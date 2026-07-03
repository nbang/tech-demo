"""Core engine: introspect an RDF graph's ontology, then answer questions as SPARQL.

The graph's ontology is small enough to hand to the model whole (classes + property shapes),
alongside real example triples for grounding — so there is no retrieval/vector step. For very
large graphs (live endpoints with hundreds of classes) a schema-selection step would go in
`_build_prompt`; see the README's roadmap.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from . import graph, llm
from .config import settings

_REGISTRY = settings.data_dir / "registry.json"

SYSTEM_PROMPT = """You are an expert in SPARQL and RDF knowledge graphs. Convert the user's question into ONE SPARQL query for the graph described below.

You are given the graph's prefixes, its ontology (classes + properties), and a block of REAL example
triples. Ground your query in that example data: use its exact prefixes and IRIs, and follow how the
entities actually link together. Never invent classes, properties, or IRIs.

Respond with ONLY a JSON object:
{"sparql": "<the query, or empty string>", "explanation": "<one sentence>", "classes_used": ["prefix:Class", ...]}

Example (different ontology — copy the pattern, not the terms):
{"sparql": "PREFIX g: <http://ex/#>\\nPREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\\nSELECT ?name WHERE {\\n  ?city rdfs:label \\"Lyon\\" ; g:within+ ?region .\\n  ?region a g:Region ; rdfs:label ?name .\\n}", "explanation": "Walks g:within+ from Lyon up to every containing region.", "classes_used": ["g:City", "g:Region"]}"""


def _graph_id(source: str) -> str:
    return hashlib.sha1(source.encode()).hexdigest()[:12]


def _read_registry() -> dict:
    if _REGISTRY.exists():
        return json.loads(_REGISTRY.read_text())
    return {}


def _write_registry(reg: dict) -> None:
    _REGISTRY.write_text(json.dumps(reg, indent=2))


def _prefix_block(prefixes: dict[str, str]) -> str:
    return "\n".join(f"PREFIX {p}: <{ns}>" for p, ns in sorted(prefixes.items()))


def _expand(curie: str, prefixes: dict[str, str]) -> str:
    """Expand a CURIE (org:Employee) back to a full IRI using the graph's prefix table."""
    if ":" in curie:
        pfx, local = curie.split(":", 1)
        if pfx in prefixes:
            return prefixes[pfx] + local
    return curie


@dataclass
class IngestResult:
    graph_id: str
    class_count: int
    name: str
    prefixes: dict[str, str]
    documents: list[str]  # per-class ontology docs — the exact context handed to the model


def ingest(source: str, name: str | None = None) -> IngestResult:
    """Introspect the graph and cache its ontology (class docs + prefixes) in the registry.

    No embeddings, no vector index: the whole ontology is small enough to hand to the model at
    generation time, so ingest is just a one-time schema snapshot.
    """
    classes = graph.introspect(source)
    if not classes:
        raise ValueError("No classes found in this graph (check the file path / endpoint URL).")

    ids = [c.curie for c in classes]
    # The class document (labels + comments + property shapes) is exactly the ontology context
    # the model needs at generation time. Cache it so /ask doesn't re-introspect.
    documents = [c.to_document() for c in classes]
    prefixes = graph.GraphSource(source).prefixes()

    graph_id = _graph_id(source)
    reg = _read_registry()
    reg[graph_id] = {
        "name": name or graph_id,
        "source": source,
        "class_count": len(classes),
        "classes": ids,
        "documents": documents,
        "prefixes": prefixes,
    }
    reg["_latest"] = graph_id
    _write_registry(reg)

    return IngestResult(
        graph_id=graph_id,
        class_count=len(classes),
        name=name or graph_id,
        prefixes=prefixes,
        documents=documents,
    )


def _resolve(graph_id: str | None) -> tuple[str, dict]:
    reg = _read_registry()
    if graph_id is None:
        graph_id = reg.get("_latest")
    if not graph_id or graph_id not in reg:
        raise ValueError("No ingested graph found. Run /ingest first.")
    return graph_id, reg[graph_id]


@dataclass
class AskResult:
    sparql: str
    explanation: str
    classes_used: list[str]


def _to_ask_result(data: dict) -> AskResult:
    return AskResult(
        sparql=(data.get("sparql") or "").strip(),
        explanation=data.get("explanation", ""),
        classes_used=data.get("classes_used", []),
    )


def _build_prompt(question: str, meta: dict) -> str:
    """Assemble the user prompt: prefixes + full ontology + REAL example triples."""
    ids = meta["classes"]
    context = "\n\n".join(meta.get("documents", []))
    prefixes = meta.get("prefixes", {})
    prefix_table = _prefix_block(prefixes)

    # Ground the model in REAL data: pull example triples for the classes so it sees actual IRIs,
    # literal values, and how entities link (the connectivity an abstract schema hides).
    context_iris = [_expand(i, prefixes) for i in ids]
    try:
        examples = graph.sample_triples(meta["source"], context_iris)
    except Exception:
        examples = ""  # sampling is best-effort; never block generation on it

    return (
        f"# Prefixes available:\n{prefix_table}\n\n"
        f"# Ontology (classes + property shapes):\n{context}\n\n"
        f"# Example instance data (REAL triples — copy these exact prefixes/IRIs, and match a named\n"
        f"#   entity by the label literal shown):\n{examples}\n\n"
        f"# Question: {question}"
    )


def ask(question: str, graph_id: str | None = None) -> str:
    """Generate SPARQL for the question and return ONLY the query text (does not execute)."""
    _, meta = _resolve(graph_id)
    result = _to_ask_result(llm.generate_sparql(SYSTEM_PROMPT, _build_prompt(question, meta)))
    return result.sparql


def execute(sparql: str, graph_id: str | None = None) -> "graph.QueryResult":
    """Execute a raw SPARQL query against the ingested graph (read-only — updates are refused)."""
    _, meta = _resolve(graph_id)
    return graph.run_query(meta["source"], sparql)


_REPAIR = """
The query you just wrote raised an error. Here is what you produced:
{sparql}

Error from the SPARQL engine:
{problem}

Fix the SYNTAX/term error and return a corrected query as the SAME JSON object. Re-check the example
instance data above for the exact prefixes, property names, and IRIs."""


@dataclass
class AnswerResult:
    ask: AskResult
    result: "graph.QueryResult | None"
    attempts: int
    error: str | None


def answer(question: str, graph_id: str | None = None) -> AnswerResult:
    """Generate SPARQL, execute it, and self-repair on ERRORS (invalid syntax / unknown terms).

    Repair is deliberately limited to errors. A *valid* query that returns 0 rows is left alone: for a
    small model, re-prompting on "0 rows" tends to mangle an otherwise-fine query into a broken one, and
    an empty result can be the correct answer. Syntax/term errors, by contrast, are almost always
    fixable from the engine's own error message plus the example data.
    """
    _, meta = _resolve(graph_id)
    base_prompt = _build_prompt(question, meta)

    prompt = base_prompt
    last: AskResult | None = None
    error: str | None = None

    for attempt in range(1, settings.max_attempts + 1):
        last = _to_ask_result(llm.generate_sparql(SYSTEM_PROMPT, prompt))
        if not last.sparql:
            error = "model produced no SPARQL"
        else:
            try:
                qr = graph.run_query(meta["source"], last.sparql)
            except Exception as e:
                error = str(e)
            else:
                return AnswerResult(ask=last, result=qr, attempts=attempt, error=None)
        if attempt < settings.max_attempts:
            prompt = base_prompt + _REPAIR.format(sparql=last.sparql or "(empty)", problem=error)

    return AnswerResult(ask=last, result=None, attempts=settings.max_attempts, error=error)
