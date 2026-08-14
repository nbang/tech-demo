// Copyright 2026.
//
// Command nl2query-graph is a demo of the ADK-Go v2.0 graph-based workflow
// engine applied to a natural-language → query pipeline. It is a HYBRID,
// fan-out/parallel pipeline (modelled on adk-go's examples/workflow/complex)
// with a human-in-the-loop review step in the middle:
//
//	START ─┬─▶ gen_sql(LLM)    ─┐
//	       └─▶ gen_sparql(LLM)  ─┤                (generation runs in parallel)
//	                            ▼
//	                   gather_gen (JoinNode: both queries)
//	                            ▼
//	                   review (HITL: approve, or revise either query)
//	                            ▼
//	       ┌────────────────────┴────────────────────┐
//	       ▼                                          ▼
//	   exec_sql(SQLite)                        exec_sparql(TTL)   (execute in parallel)
//	       └────────────────────┬────────────────────┘
//	                            ▼
//	                   gather_res (JoinNode: both results)
//	                            ▼
//	                   format ─▶ synthesize(LLM)
//
// The LLM generates a SQL and a SPARQL query in parallel; a single review step
// shows both and lets the human approve or edit them; the approved queries are
// executed in parallel against their stores; and a synthesis agent reconciles
// the two result sets into one grounded answer.
//
// Configure via .env (see .env.example), then:
//
//	go mod tidy
//	go run . console
package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"strings"

	"google.golang.org/adk/v2/agent"
	"google.golang.org/adk/v2/agent/llmagent"
	"google.golang.org/adk/v2/agent/workflowagent"
	"google.golang.org/adk/v2/cmd/launcher"
	"google.golang.org/adk/v2/cmd/launcher/full"
	"google.golang.org/adk/v2/session"
	"google.golang.org/adk/v2/workflow"
)

const sparqlGenInstruction = `Translate the user's question into a SPARQL SELECT query.

Schema (prefix ex: <http://example.org/>):
  ex:Product  — ex:name (string), ex:price (number), ex:category (string)
  ex:Person   — ex:name (string), ex:knows (-> another ex:Person)

Rules:
- Output ONLY the query. No prose, no explanation, no markdown code fences.
- Begin with: PREFIX ex: <http://example.org/>
- Use only basic triple patterns "s p o ." and, if needed, FILTER(?var OP number)
  where OP is one of < <= > >= = !=.
- Do NOT use OPTIONAL, UNION, aggregates, GROUP BY, or property paths.`

const sqlGenInstruction = `Translate the user's question into a single SQLite SELECT query.

Schema:
  products(id INTEGER, name TEXT, price REAL, category TEXT)
  customers(id INTEGER, name TEXT, city TEXT)

Rules:
- Output ONLY the SQL. No prose, no explanation, no markdown code fences.
- Standard SQLite SELECT syntax. A trailing semicolon is optional.`

const synthesisInstruction = `You are given the SAME user question answered independently by two backends:
a relational database (SQL over SQLite) and a knowledge graph (SPARQL over RDF).

Produce ONE concise answer to the user's question, grounded ONLY on the two result
sets provided below:
- If both backends agree, state the answer plainly and note that they agree.
- If they differ (different rows or counts), summarise each and point out the discrepancy.
- If one backend failed or returned nothing, answer from the other and say so.
Do not invent data beyond the provided results.`

// genResult carries a generated query and its language between nodes.
type genResult struct {
	Lang  string
	Query string
}

// reviewedQueries carries the (possibly human-edited) queries past the HITL
// review node to the parallel execution branches.
type reviewedQueries struct {
	SQL    string
	SPARQL string
}

// Node names. Generation/execution node names double as JoinNode map keys.
const (
	nGenSQL     = "gen_sql"
	nGenSPARQL  = "gen_sparql"
	nExecSQL    = "exec_sql"
	nExecSPARQL = "exec_sparql"
)

func boolPtr(b bool) *bool { return &b }

// userMessage reads the original user question from ctx.UserContent().
func userMessage(ctx agent.Context) string {
	uc := ctx.UserContent()
	if uc == nil {
		return ""
	}
	var sb strings.Builder
	for _, p := range uc.Parts {
		sb.WriteString(p.Text)
	}
	return strings.TrimSpace(sb.String())
}

// stripFences removes ```lang ... ``` fences if the model wraps its output.
func stripFences(s string) string {
	s = strings.TrimSpace(s)
	if strings.HasPrefix(s, "```") {
		if i := strings.Index(s, "\n"); i >= 0 {
			s = s[i+1:]
		}
		s = strings.TrimSuffix(strings.TrimSpace(s), "```")
	}
	return strings.TrimSpace(s)
}

// applyRevisions interprets the human's reply to the review prompt. An empty
// reply or "yes"/"y" accepts both generated queries; otherwise any line prefixed
// "sql:" or "sparql:" overrides that query (the rest keep the generated value).
func applyRevisions(reply, sqlGen, sparqlGen string) reviewedQueries {
	out := reviewedQueries{SQL: sqlGen, SPARQL: sparqlGen}
	r := strings.TrimSpace(reply)
	if r == "" || strings.EqualFold(r, "yes") || strings.EqualFold(r, "y") {
		return out
	}
	for _, line := range strings.Split(r, "\n") {
		line = strings.TrimSpace(line)
		switch {
		case strings.HasPrefix(strings.ToLower(line), "sql:"):
			out.SQL = strings.TrimSpace(line[len("sql:"):])
		case strings.HasPrefix(strings.ToLower(line), "sparql:"):
			out.SPARQL = strings.TrimSpace(line[len("sparql:"):])
		}
	}
	return out
}

// buildHybrid wires the fan-out → join → HITL review → fan-out → join →
// synthesis graph. It is separate from main so tests can validate the graph
// (workflowagent.New checks the edges) without a live endpoint.
func buildHybrid(llm *OpenAIModel, sqlStore *SQLStore, tripleStore *TripleStore) (agent.Agent, error) {
	// --- parallel generation (real text2sql / text2sparql), with retries ---
	genSQL := workflow.NewFunctionNode(nGenSQL,
		func(ctx agent.Context, _ any) (genResult, error) {
			q, err := llm.Complete(ctx, sqlGenInstruction, userMessage(ctx))
			if err != nil {
				log.Printf("gen_sql: %v", err) // don't kill the parallel run
				return genResult{Lang: "sql"}, nil
			}
			return genResult{Lang: "sql", Query: stripFences(q)}, nil
		},
		workflow.NodeConfig{RetryConfig: workflow.DefaultRetryConfig()},
	)
	genSPARQL := workflow.NewFunctionNode(nGenSPARQL,
		func(ctx agent.Context, _ any) (genResult, error) {
			q, err := llm.Complete(ctx, sparqlGenInstruction, userMessage(ctx))
			if err != nil {
				log.Printf("gen_sparql: %v", err)
				return genResult{Lang: "sparql"}, nil
			}
			return genResult{Lang: "sparql", Query: stripFences(q)}, nil
		},
		workflow.NodeConfig{RetryConfig: workflow.DefaultRetryConfig()},
	)

	// Join both generated queries into one map so a single review step sees both.
	gatherGen := workflow.NewJoinNode("gather_gen")

	// --- HITL review: approve or revise either query (re-entry node) ---
	review := workflow.NewEmittingFunctionNode[map[string]any, reviewedQueries]("review",
		func(ctx agent.Context, in map[string]any, emit func(*session.Event) error) (reviewedQueries, error) {
			sqlGen, _ := in[nGenSQL].(genResult)
			sparqlGen, _ := in[nGenSPARQL].(genResult)

			msg := fmt.Sprintf(`Review the generated queries before execution.
Reply "yes" to run both as-is, or override one/both with lines like:
  sql: SELECT ...
  sparql: PREFIX ex: <http://example.org/> SELECT ...

[SQL]
%s

[SPARQL]
%s`, sqlGen.Query, sparqlGen.Query)

			reply, err := workflow.ResumeOrRequestInput(ctx, emit, session.RequestInput{
				InterruptID: "review-" + ctx.InvocationID(),
				Message:     msg,
			})
			if err != nil {
				return reviewedQueries{}, err // ErrNodeInterrupted on the first pass
			}
			return applyRevisions(fmt.Sprint(reply), sqlGen.Query, sparqlGen.Query), nil
		},
		workflow.NodeConfig{RerunOnResume: boolPtr(true)},
	)

	// --- parallel execution of the approved queries ---
	// Execution errors are folded into the output string, so one backend failing
	// never deadlocks the downstream join.
	execSQL := workflow.NewFunctionNode(nExecSQL,
		func(ctx agent.Context, in reviewedQueries) (string, error) {
			if strings.TrimSpace(in.SQL) == "" {
				return "(no SQL query)", nil
			}
			res, err := sqlStore.Query(ctx, in.SQL)
			if err != nil {
				return fmt.Sprintf("(SQL failed: %v)\nQuery:\n%s", err, in.SQL), nil
			}
			return fmt.Sprintf("Query:\n%s\n\nResult:\n%s", in.SQL, res), nil
		},
		workflow.NodeConfig{},
	)
	execSPARQL := workflow.NewFunctionNode(nExecSPARQL,
		func(ctx agent.Context, in reviewedQueries) (string, error) {
			if strings.TrimSpace(in.SPARQL) == "" {
				return "(no SPARQL query)", nil
			}
			res, err := tripleStore.Query(in.SPARQL)
			if err != nil {
				return fmt.Sprintf("(SPARQL failed: %v)\nQuery:\n%s", err, in.SPARQL), nil
			}
			return fmt.Sprintf("Query:\n%s\n\nResult:\n%s", in.SPARQL, res), nil
		},
		workflow.NodeConfig{},
	)

	// --- fan-in results + format + synthesis ---
	gatherRes := workflow.NewJoinNode("gather_res")

	format := workflow.NewFunctionNode("format",
		func(ctx agent.Context, gathered map[string]any) (string, error) {
			var sb strings.Builder
			fmt.Fprintf(&sb, "User question: %s\n\n", userMessage(ctx))
			fmt.Fprintf(&sb, "=== Relational backend (SQL / SQLite) ===\n%s\n\n", fmt.Sprint(gathered[nExecSQL]))
			fmt.Fprintf(&sb, "=== Knowledge-graph backend (SPARQL / RDF) ===\n%s\n", fmt.Sprint(gathered[nExecSPARQL]))
			return sb.String(), nil
		},
		workflow.NodeConfig{},
	)

	synthAgent, err := llmagent.New(llmagent.Config{
		Name:        "synthesize",
		Model:       llm,
		Description: "reconciles the relational and graph results into one answer",
		Instruction: synthesisInstruction,
	})
	if err != nil {
		return nil, fmt.Errorf("synthesis agent: %w", err)
	}
	synthNode, err := workflow.NewAgentNode(synthAgent, workflow.NodeConfig{})
	if err != nil {
		return nil, fmt.Errorf("synthesis node: %w", err)
	}

	eb := workflow.NewEdgeBuilder()
	eb.AddFanOut(workflow.Start, genSQL, genSPARQL) // parallel generation
	eb.AddFanIn(gatherGen, genSQL, genSPARQL)       // join both queries
	eb.Add(gatherGen, review)                       // single HITL review of both
	eb.AddFanOut(review, execSQL, execSPARQL)       // parallel execution
	eb.AddFanIn(gatherRes, execSQL, execSPARQL)     // join both results
	eb.Add(gatherRes, format)
	eb.Add(format, synthNode)

	return workflowagent.New(workflowagent.Config{
		Name:        "nl2query_hybrid",
		Description: "generates SQL + SPARQL in parallel, reviews with a human, executes, and synthesises one answer",
		Edges:       eb.Build(),
		SubAgents:   []agent.Agent{synthAgent},
	})
}

func main() {
	ctx := context.Background()

	cfg, err := LoadConfig()
	if err != nil {
		log.Fatalf("config: %v", err)
	}

	llm := NewOpenAIModel(cfg.Model, cfg.BaseURL, cfg.APIKey)
	log.Printf("model %q at %s", cfg.Model, cfg.BaseURL)

	sqlStore, err := OpenSQLStore(cfg.SQLitePath)
	if err != nil {
		log.Fatalf("sqlite: %v", err)
	}
	defer sqlStore.Close()
	log.Printf("sqlite ready: %s", cfg.SQLitePath)

	tripleStore, err := OpenTripleStore(cfg.TTLPath)
	if err != nil {
		log.Fatalf("ttl: %v", err)
	}
	log.Printf("ttl ready: %s (%d triples)", cfg.TTLPath, tripleStore.Count())

	rootAgent, err := buildHybrid(llm, sqlStore, tripleStore)
	if err != nil {
		log.Fatalf("build graph: %v", err)
	}

	log.Printf("nl2query-graph ready — ask a question; review both queries, then they execute in parallel")

	launcherCfg := &launcher.Config{AgentLoader: agent.NewSingleLoader(rootAgent)}
	l := full.NewLauncher()
	if err := l.Execute(ctx, launcherCfg, os.Args[1:]); err != nil {
		log.Fatalf("Run failed: %v\n\n%s", err, l.CommandLineSyntax())
	}
}
