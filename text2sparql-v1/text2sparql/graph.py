"""RDF connectivity: ontology introspection (classes + properties) and SPARQL execution.

A *source* is a path to a local RDF file (Turtle, RDF/XML, N-Triples, JSON-LD…), wrapped in an
rdflib Graph so introspection and query execution share one path.
"""

from __future__ import annotations

import datetime as _dt
import decimal
from dataclasses import dataclass, field
from typing import Any

from rdflib import Graph, Literal, Namespace, URIRef  # type: ignore[import]
from rdflib.namespace import OWL, RDF, RDFS, SKOS, XSD  # type: ignore[import]

# schema.org — a common domain vocabulary (schema:Person, schema:Product, …). Seeded so its
# CURIEs read as schema:… even when the graph doesn't declare the prefix itself.
SCHEMA = Namespace("https://schema.org/")

# Fixed operational limits (kept simple — not env-tunable in this version).
MAX_CLASSES = 200    # cap on classes introspected, to keep ingest cheap on large graphs
SAMPLE_LIMIT = 2000  # cap on the per-class triple scan used to infer property shapes
MAX_ROWS = 500       # cap on rows returned from a query

# Schema/meta vocabularies — these define the ontology language, not the domain,
# so we never surface their terms (owl:Class, rdfs:Class, …) as queryable classes.
_META_NAMESPACES = (str(RDF), str(RDFS), str(OWL), str(XSD))


class GraphSource:
    """Query surface over a local RDF file."""

    def __init__(self, source: str):
        self.source = source
        # bind_namespaces="none": don't preload rdflib's large well-known table — its built-in
        # `org`/`geo`/`foaf`/… prefixes would collide with the graph's own and get aliased to
        # org1:, geo1:, etc. We want the CURIEs to reflect the graph's declared prefixes.
        self.graph = Graph(bind_namespaces="none")
        self.graph.parse(source)  # rdflib sniffs the format from the file extension / content
        # Seed the core prefixes so generated SPARQL reads naturally; the graph's own
        # @prefix declarations take precedence and are left untouched.
        for pfx, ns in (("rdf", RDF), ("rdfs", RDFS), ("owl", OWL), ("xsd", XSD), ("skos", SKOS), ("schema", SCHEMA)):
            self.graph.namespace_manager.bind(pfx, ns, replace=False)

    def query(self, sparql: str):
        return self.graph.query(sparql)

    def curie(self, iri: str) -> str:
        """Shorten an IRI to a CURIE, auto-binding a prefix if needed (n3 form, e.g. ex:Order)."""
        try:
            return self.graph.namespace_manager.normalizeUri(URIRef(iri))
        except Exception:
            return f"<{iri}>"

    def prefixes(self) -> dict[str, str]:
        return {p: str(n) for p, n in self.graph.namespace_manager.namespaces()}


@dataclass
class Property:
    iri: str
    curie: str
    ranges: list[str] = field(default_factory=list)  # CURIEs: datatypes or object classes


@dataclass
class ClassInfo:
    iri: str
    curie: str
    label: str | None = None
    comment: str | None = None
    instance_count: int = 0
    super_classes: list[str] = field(default_factory=list)  # CURIEs of direct rdfs:subClassOf parents
    sub_classes: list[str] = field(default_factory=list)  # CURIEs of direct children (filled post-pass)
    properties: list[Property] = field(default_factory=list)

    def to_document(self) -> str:
        """Human + LLM readable description of the class — this is the ontology context we prompt with."""
        head = f"Class: {self.curie}"
        if self.label:
            head += f'  (rdfs:label "{self.label}")'
        lines = [head]
        if self.super_classes:
            lines.append(f"Subclass of: {', '.join(self.super_classes)}")
        if self.sub_classes:
            lines.append(f"Subclasses: {', '.join(self.sub_classes)}")
        if self.comment:
            lines.append(f"Description: {self.comment}")
        if self.instance_count:
            lines.append(f"Instances: {self.instance_count}")
        if self.properties:
            lines.append("Properties (predicate -> range):")
            for p in self.properties:
                # Cap ranges: when types are materialized, an object can carry its whole
                # superclass chain — show the first few rather than a noisy union.
                shown = p.ranges[:3]
                rng = " | ".join(shown) + (" | …" if len(p.ranges) > 3 else "") if shown else "?"
                lines.append(f"  - {p.curie} -> {rng}")
        return "\n".join(lines)


def _opt_text(graph_source: GraphSource, subject: str, predicate) -> str | None:
    q = f"""SELECT ?v WHERE {{ <{subject}> <{predicate}> ?v . FILTER(isLiteral(?v)) }} LIMIT 1"""
    for row in graph_source.query(q):
        return str(row[0])
    return None


def introspect(source: str) -> list[ClassInfo]:
    """Discover the classes used in the graph and, for each, the predicates and ranges seen on its instances."""
    gs = GraphSource(source)

    # 1. Classes — both declared (owl/rdfs:Class) and actually instantiated.
    meta_filter = " ".join(
        f'FILTER(!STRSTARTS(STR(?cls), "{ns}"))' for ns in _META_NAMESPACES
    )
    class_q = f"""
    SELECT DISTINCT ?cls WHERE {{
      {{ ?cls a <{OWL.Class}> }} UNION {{ ?cls a <{RDFS.Class}> }} UNION {{ ?s a ?cls }}
      FILTER(isIRI(?cls))
      {meta_filter}
    }} LIMIT {MAX_CLASSES}
    """
    class_iris = [str(r[0]) for r in gs.query(class_q)]
    if not class_iris:
        raise ValueError(
            "No classes found in this graph. Provide RDF with rdf:type statements, "
            "or a SPARQL endpoint that exposes instance data."
        )

    classes: list[ClassInfo] = []
    for iri in class_iris:
        info = ClassInfo(iri=iri, curie=gs.curie(iri))
        info.label = _opt_text(gs, iri, RDFS.label)
        info.comment = _opt_text(gs, iri, RDFS.comment)

        # Instance count.
        for r in gs.query(f"SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE {{ ?s a <{iri}> }}"):
            info.instance_count = int(r[0]) if r[0] is not None else 0

        # Direct superclasses (rdfs:subClassOf) — the graph's type hierarchy. We surface
        # this so the model can write subclass-aware queries (e.g. ?x a/rdfs:subClassOf* C).
        sup_q = f"SELECT DISTINCT ?sup WHERE {{ <{iri}> <{RDFS.subClassOf}> ?sup . FILTER(isIRI(?sup)) }}"
        for r in gs.query(sup_q):
            sup = str(r[0])
            if sup == iri or any(sup.startswith(ns) for ns in _META_NAMESPACES):
                continue
            info.super_classes.append(gs.curie(sup))

        # 2. Predicates seen on instances of this class, with their ranges.
        prop_q = f"""
        SELECT DISTINCT ?p ?dt ?otype WHERE {{
          ?s a <{iri}> ; ?p ?o .
          OPTIONAL {{ ?o a ?otype }}
          BIND(DATATYPE(?o) AS ?dt)
        }} LIMIT {SAMPLE_LIMIT}
        """
        props: dict[str, Property] = {}
        for r in gs.query(prop_q):
            p_iri = str(r["p"])
            if p_iri == str(RDF.type):
                continue
            prop = props.get(p_iri)
            if prop is None:
                prop = Property(iri=p_iri, curie=gs.curie(p_iri))
                props[p_iri] = prop
            rng = None
            if r["otype"] is not None:
                rng = gs.curie(str(r["otype"]))
            elif r["dt"] is not None:
                rng = gs.curie(str(r["dt"]))
            if rng and rng not in prop.ranges:
                prop.ranges.append(rng)
        info.properties = list(props.values())
        classes.append(info)

    # Reverse the subClassOf edges so each class also lists its direct children.
    by_curie = {c.curie: c for c in classes}
    for c in classes:
        for sup in c.super_classes:
            parent = by_curie.get(sup)
            if parent is not None and c.curie not in parent.sub_classes:
                parent.sub_classes.append(c.curie)

    return classes


# Literal datatypes we render WITHOUT quotes, so the model sees a number/bool as a number/bool
# (and writes numeric FILTERs, not string comparisons). Plain strings stay quoted; other typed
# literals (e.g. xsd:dateTime) keep their ^^type so the model uses the right literal form.
_BARE_DT = frozenset({
    XSD.integer, XSD.decimal, XSD.float, XSD.double, XSD.boolean,
    XSD.int, XSD.long, XSD.short, XSD.nonNegativeInteger, XSD.positiveInteger,
})


def _term_text(gs: GraphSource, term: Any) -> str:
    """Render an RDF term for an example-triples block: IRIs as CURIEs, literals faithfully typed."""
    if isinstance(term, URIRef):
        return gs.curie(str(term))
    if isinstance(term, Literal):
        dt = term.datatype
        if dt in _BARE_DT:
            return str(term)  # 500000, 89.0, true — unquoted, so numeric semantics are visible
        if dt is not None and dt != XSD.string:
            return f'"{term}"^^{gs.curie(str(dt))}'  # e.g. "2026-06-02T10:00:00"^^xsd:dateTime
        return f'"{term}"'
    return f'"{term}"'


def sample_triples(source: str, class_iris: list[str], max_subjects: int = 12, per_class: int = 2) -> str:
    """Return REAL example triples (compact Turtle with CURIEs) for instances of the given classes.

    This grounds the LLM in actual IRIs, literal values, and — crucially — how entities link to
    each other (e.g. that ex:tom org:reportsTo ex:mei org:reportsTo ex:raj), which an abstract
    per-class schema cannot convey. Bounded by max_subjects so it stays small on large graphs.
    """
    gs = GraphSource(source)
    seen: set[str] = set()
    blocks: list[str] = []
    for iri in class_iris:
        if len(seen) >= max_subjects:
            break
        # ORDER BY ?s so the sample is deterministic run-to-run (LIMIT without an order is
        # arbitrary, which would make generation — and thus eval — flaky).
        for r in gs.query(f"SELECT DISTINCT ?s WHERE {{ ?s a <{iri}> }} ORDER BY ?s LIMIT {per_class}"):
            s = str(r[0])
            if s in seen:
                continue
            seen.add(s)
            preds: dict[str, list[str]] = {}
            for pr in gs.query(f"SELECT ?p ?o WHERE {{ <{s}> ?p ?o }} ORDER BY ?p ?o"):
                p = "a" if str(pr["p"]) == str(RDF.type) else gs.curie(str(pr["p"]))
                preds.setdefault(p, []).append(_term_text(gs, pr["o"]))
            if not preds:
                continue
            # rdf:type first (shows the class hierarchy), then the rest.
            ordered = sorted(preds.items(), key=lambda kv: (kv[0] != "a", kv[0]))
            body = " ;\n  ".join(f"{p} {', '.join(objs)}" for p, objs in ordered)
            blocks.append(f"{gs.curie(s)}\n  {body} .")
            if len(seen) >= max_subjects:
                break
    return "\n".join(blocks)


def _json_safe(value: Any) -> Any:
    if isinstance(value, URIRef):
        return str(value)
    if isinstance(value, Literal):
        py = value.toPython()
        return _json_safe(py) if py is not value else str(value)
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (_dt.datetime, _dt.date, _dt.time)):
        return value.isoformat()
    if isinstance(value, (_dt.timedelta,)):
        return str(value)
    if value is None:
        return None
    return str(value)


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[list[Any]]
    rowcount: int
    truncated: bool


def run_query(source: str, sparql: str) -> QueryResult:
    """Execute a read-only SELECT/ASK query and normalize the result. Caps results at MAX_ROWS."""
    gs = GraphSource(source)
    result = gs.query(sparql)

    # ASK → single boolean.
    if result.type == "ASK":
        return QueryResult(columns=["ask"], rows=[[bool(result.askAnswer)]], rowcount=1, truncated=False)

    # SELECT → variable bindings.
    columns = [str(v) for v in result.vars]
    fetched = list(result)
    truncated = len(fetched) > MAX_ROWS
    rows = [[_json_safe(row[v]) for v in result.vars] for row in fetched[:MAX_ROWS]]
    return QueryResult(columns=columns, rows=rows, rowcount=len(rows), truncated=truncated)
