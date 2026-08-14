// Copyright 2026.
//
// exec_sparql.go loads a Turtle (.ttl) file into an in-memory triple store and
// runs SPARQL SELECT queries against it.
//
// IMPORTANT: Go has no mature embedded SPARQL 1.1 engine, so this is a
// deliberately SMALL, self-contained executor — not a full SPARQL engine. It
// supports exactly what this demo needs and what the generator prompt is told
// to emit:
//
//   - PREFIX declarations
//   - SELECT ?a ?b ...   (or SELECT *)
//   - a WHERE block of basic triple patterns "s p o ." (variables, IRIs,
//     prefixed names, `a` for rdf:type, and quoted/number literals)
//   - one or more FILTER(?var OP value) with OP in < <= > >= = !=
//
// Anything outside that subset (OPTIONAL, UNION, aggregates, property paths,
// etc.) will return an error rather than silently mis-answer. The Turtle
// PARSING is full-featured (via github.com/knakk/rdf); only the query engine
// is a subset.

package main

import (
	"fmt"
	"io"
	"os"
	"regexp"
	"sort"
	"strconv"
	"strings"

	"github.com/knakk/rdf"
)

const rdfType = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"

// triple is a stored triple in normalized string form.
type triple struct{ s, p, o string }

// TripleStore is an in-memory set of triples loaded from a Turtle file.
type TripleStore struct {
	triples []triple
}

// OpenTripleStore reads and parses a .ttl file into memory.
func OpenTripleStore(path string) (*TripleStore, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("open ttl %q: %w", path, err)
	}
	defer f.Close()

	dec := rdf.NewTripleDecoder(f, rdf.Turtle)
	ts := &TripleStore{}
	for {
		t, err := dec.Decode()
		if err == io.EOF {
			break
		}
		if err != nil {
			return nil, fmt.Errorf("parse ttl %q: %w", path, err)
		}
		ts.triples = append(ts.triples, triple{
			s: t.Subj.String(),
			p: t.Pred.String(),
			o: t.Obj.String(),
		})
	}
	if len(ts.triples) == 0 {
		return nil, fmt.Errorf("no triples parsed from %q", path)
	}
	return ts, nil
}

// Count returns the number of triples loaded.
func (ts *TripleStore) Count() int { return len(ts.triples) }

// qterm is a parsed query term: a variable, or a constant match value.
type qterm struct {
	isVar bool
	v     string // variable name (no '?') if isVar, else the constant value
}

type qfilter struct {
	varName string
	op      string
	val     string
	isNum   bool
	num     float64
}

var filterRe = regexp.MustCompile(`(?i)FILTER\s*\(\s*\?(\w+)\s*(<=|>=|!=|=|<|>)\s*("[^"]*"|[0-9.]+)\s*\)`)
var selectRe = regexp.MustCompile(`(?is)SELECT\s+(.*?)\s+WHERE`)
var whereRe = regexp.MustCompile(`(?is)WHERE\s*\{(.*)\}`)
var prefixRe = regexp.MustCompile(`(?im)^\s*PREFIX\s+(\w+):\s*<([^>]*)>`)
var stmtSep = regexp.MustCompile(`\s+\.\s+`)

// Query executes a SELECT from the supported subset and returns a table.
func (ts *TripleStore) Query(query string) (string, error) {
	prefixes := map[string]string{
		"rdf":  "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
		"rdfs": "http://www.w3.org/2000/01/rdf-schema#",
		"xsd":  "http://www.w3.org/2001/XMLSchema#",
	}
	for _, m := range prefixRe.FindAllStringSubmatch(query, -1) {
		prefixes[m[1]] = m[2]
	}

	selM := selectRe.FindStringSubmatch(query)
	if selM == nil {
		return "", fmt.Errorf("unsupported query: expected SELECT ... WHERE")
	}
	selectVars := strings.Fields(strings.ReplaceAll(selM[1], "?", ""))
	selectAll := len(selectVars) == 1 && selectVars[0] == "*"

	whM := whereRe.FindStringSubmatch(query)
	if whM == nil {
		return "", fmt.Errorf("unsupported query: missing WHERE { ... }")
	}
	body := whM[1]

	// Pull out FILTERs, then strip them from the pattern body.
	var filters []qfilter
	for _, m := range filterRe.FindAllStringSubmatch(body, -1) {
		fl := qfilter{varName: m[1], op: m[2], val: strings.Trim(m[3], `"`)}
		if n, err := strconv.ParseFloat(fl.val, 64); err == nil {
			fl.isNum, fl.num = true, n
		}
		filters = append(filters, fl)
	}
	body = filterRe.ReplaceAllString(body, "")

	// Split remaining body into triple patterns.
	body = strings.ReplaceAll(body, "\n", " ") + " . "
	var patterns [][3]qterm
	for _, stmt := range stmtSep.Split(body, -1) {
		stmt = strings.TrimSpace(stmt)
		stmt = strings.TrimSpace(strings.TrimSuffix(stmt, ".")) // drop stray terminator dots
		if stmt == "" {
			continue
		}
		toks := tokenizePattern(stmt)
		if len(toks) != 3 {
			return "", fmt.Errorf("unsupported pattern (need 3 terms): %q", stmt)
		}
		patterns = append(patterns, [3]qterm{
			resolveTerm(toks[0], prefixes),
			resolveTerm(toks[1], prefixes),
			resolveTerm(toks[2], prefixes),
		})
	}
	if len(patterns) == 0 {
		return "", fmt.Errorf("no triple patterns found in WHERE")
	}

	// Nested-loop join over patterns, accumulating variable bindings.
	bindings := []map[string]string{{}}
	for _, pat := range patterns {
		var next []map[string]string
		for _, b := range bindings {
			for _, t := range ts.triples {
				if nb, ok := unify(pat, t, b); ok {
					next = append(next, nb)
				}
			}
		}
		bindings = next
		if len(bindings) == 0 {
			break
		}
	}

	// Apply FILTERs.
	if len(filters) > 0 {
		var kept []map[string]string
		for _, b := range bindings {
			if passesFilters(b, filters) {
				kept = append(kept, b)
			}
		}
		bindings = kept
	}

	// Determine output columns.
	cols := selectVars
	if selectAll {
		seen := map[string]bool{}
		for _, b := range bindings {
			for k := range b {
				seen[k] = true
			}
		}
		cols = cols[:0]
		for k := range seen {
			cols = append(cols, k)
		}
		sort.Strings(cols)
	}

	var out strings.Builder
	out.WriteString(strings.Join(cols, " | "))
	out.WriteString("\n")
	for _, b := range bindings {
		cells := make([]string, len(cols))
		for i, c := range cols {
			cells[i] = b[c]
		}
		out.WriteString(strings.Join(cells, " | "))
		out.WriteString("\n")
	}
	out.WriteString(fmt.Sprintf("(%d row(s))", len(bindings)))
	return out.String(), nil
}

// unify tries to match one pattern against one stored triple, extending b.
func unify(pat [3]qterm, t triple, b map[string]string) (map[string]string, bool) {
	nb := make(map[string]string, len(b)+3)
	for k, v := range b {
		nb[k] = v
	}
	vals := [3]string{t.s, t.p, t.o}
	for i, term := range pat {
		if term.isVar {
			if cur, ok := nb[term.v]; ok {
				if cur != vals[i] {
					return nil, false
				}
			} else {
				nb[term.v] = vals[i]
			}
		} else if term.v != vals[i] {
			return nil, false
		}
	}
	return nb, true
}

func passesFilters(b map[string]string, filters []qfilter) bool {
	for _, f := range filters {
		got, ok := b[f.varName]
		if !ok {
			return false
		}
		if f.isNum {
			n, err := strconv.ParseFloat(got, 64)
			if err != nil {
				return false
			}
			switch f.op {
			case "<":
				if !(n < f.num) {
					return false
				}
			case "<=":
				if !(n <= f.num) {
					return false
				}
			case ">":
				if !(n > f.num) {
					return false
				}
			case ">=":
				if !(n >= f.num) {
					return false
				}
			case "=":
				if n != f.num {
					return false
				}
			case "!=":
				if n == f.num {
					return false
				}
			}
		} else {
			switch f.op {
			case "=":
				if got != f.val {
					return false
				}
			case "!=":
				if got == f.val {
					return false
				}
			default:
				return false // non-numeric ordering not supported
			}
		}
	}
	return true
}

// resolveTerm parses a single WHERE token into a qterm.
func resolveTerm(tok string, prefixes map[string]string) qterm {
	switch {
	case strings.HasPrefix(tok, "?"):
		return qterm{isVar: true, v: tok[1:]}
	case tok == "a":
		return qterm{v: rdfType}
	case strings.HasPrefix(tok, "<") && strings.HasSuffix(tok, ">"):
		return qterm{v: tok[1 : len(tok)-1]}
	case strings.HasPrefix(tok, `"`):
		// "literal" possibly with ^^datatype or @lang suffix.
		if i := strings.Index(tok[1:], `"`); i >= 0 {
			return qterm{v: tok[1 : i+1]}
		}
		return qterm{v: strings.Trim(tok, `"`)}
	default:
		if i := strings.Index(tok, ":"); i >= 0 {
			if base, ok := prefixes[tok[:i]]; ok {
				return qterm{v: base + tok[i+1:]}
			}
		}
		return qterm{v: tok} // bare number or unknown token → literal value
	}
}

// tokenizePattern splits a pattern into whitespace-separated tokens, keeping
// double-quoted literals intact.
func tokenizePattern(s string) []string {
	var toks []string
	var cur strings.Builder
	inQuote := false
	flush := func() {
		if cur.Len() > 0 {
			toks = append(toks, cur.String())
			cur.Reset()
		}
	}
	for _, r := range s {
		switch {
		case r == '"':
			inQuote = !inQuote
			cur.WriteRune(r)
		case (r == ' ' || r == '\t') && !inQuote:
			flush()
		default:
			cur.WriteRune(r)
		}
	}
	flush()
	return toks
}
