# text2sparql

Natural-language → **SPARQL** for **RDF / knowledge graphs**, powered by a **self-hosted, open-source LLM** (via [Ollama](https://ollama.com)). Point it at a Turtle file or a SPARQL endpoint; it introspects the ontology, hands the model the whole schema plus **real example triples** for grounding, and turns questions like *"Which customer placed the most orders?"* into SPARQL — and can run it for you.

```
  RDF file /   ┌──────────────┐  classes + property shapes   ┌──────────────────────────┐
  endpoint ─▶  │  introspect  │ ───────────────────────────▶ │  prompt: ontology + REAL │
               └──────────────┘  + sampled example triples    │  example triples         │
                                                              └────────────┬─────────────┘
  question ────────────────────────────────────────────────────────────────▶│
                                                                  ┌──────────▼──────────┐
                                                                  │  LLM  ─▶ SPARQL ─▶ execute ─▶ rows
                                                                  └─────────────────────┘
```

The ontology is small enough to hand to the model whole — no embeddings, no vector store, no retrieval step. (Scaling to very large ontologies via a schema-selection step is on the roadmap below.) Everything runs locally.

## Stack

- **Python** CLI — ingest, ask, exec, and a reproducible `eval`. Only deps: `rdflib`, `openai`, `python-dotenv`.
- **Any OpenAI-compatible endpoint** for generation — Ollama (local, `gemma4:31b` by default), vLLM, or a hosted OpenAI/NVIDIA endpoint.
- **rdflib** for graph parsing, in-memory SPARQL, and remote endpoint querying (`SPARQLStore`).

## Setup

```bash
# 1. Self-hosted LLM
brew install ollama            # or see ollama.com
ollama serve &                 # start the daemon
ollama pull gemma4:31b         # SPARQL generation (~30B instruct; answers every eval question type)

# 2. This tool
cd text2sparql
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env           # optional — tweak models / safety
```

## Usage — CLI

Two demo graphs ship in [examples/](examples/):

- **`shop_demo.ttl`** — a flat e-commerce graph (mirrors the text2sql schema). Good first run.
- **`acme_kg.ttl`** — a **graph-native** org chart: class hierarchies (`Manager ⊑ Employee ⊑ Person`)
  and transitive relations (management chain, geographic nesting, org nesting, a skill taxonomy).
  These are answered with SPARQL **property paths** (`+`, `*`, `/`) — the things SQL can't express cleanly.

```bash
text2sparql ingest examples/acme_kg.ttl

# ask generates the SPARQL (does not execute it):
text2sparql ask "List everyone who is an employee, including managers"   # a org:Employee (types materialized)
text2sparql ask "Who does Tom report to, directly or indirectly?"        # org:reportsTo+
text2sparql ask "Which country is the ACME HQ in?"                       # basedIn/locatedIn+
text2sparql ask "List every sub-organization under ACME at any depth"    # subOrganizationOf+
text2sparql ask "Who has any kind of machine-learning skill?"            # hasSkill/skos:broader*

# exec runs a query (read-only) — paste the SPARQL that ask printed:
text2sparql exec "PREFIX org: <http://www.w3.org/ns/org#> PREFIX schema: <https://schema.org/> SELECT ?name WHERE { ?p a org:Employee ; schema:name ?name }"
```

`ask` and `exec` are split on purpose: you always see the generated SPARQL before trusting a result
(the model can drop a `PREFIX` or misread a question). The end-to-end generate → execute → **self-repair**
loop (retry once on a syntax/term error; a valid query returning 0 rows is left alone) still exists in
`engine.answer()` and is what `eval` uses to score each gold question.

You can also point it at a SPARQL endpoint. Note the introspector is built for small/medium
graphs: it runs a `COUNT(DISTINCT ?s)` + a 2000-triple scan **per class** (capped at 200 classes),
so aiming it straight at a giant public endpoint like DBpedia will hang (and trip its rate limits).
These limits are fixed constants in [text2sparql/graph.py](text2sparql/graph.py) (`MAX_CLASSES`,
`SAMPLE_LIMIT`) — lower them there if you want to experiment against a large endpoint, and expect
the arbitrary class slice may miss the class your question needs (true large-endpoint support is a
schema-selection step, see Roadmap).

## Evaluation

Accuracy is measured, not eyeballed. [examples/eval.jsonl](examples/eval.jsonl) holds gold
question → expected-answer pairs; `eval` ingests each graph, runs every question end-to-end, and
reports a pass/fail table plus an accuracy score:

```bash
text2sparql eval                       # runs examples/eval.jsonl
text2sparql eval path/to/cases.jsonl   # or your own
```

## Safety

This tool is **read-only**: it always rejects SPARQL Update (`INSERT`/`DELETE`/`LOAD`/…),
so generated queries can never mutate a store.

Ingest persists the source (file path or endpoint URL) under `.text2sparql/registry.json`
so `ask`/`execute` work across restarts. That directory is git-ignored.

## Configuration

All via env / `.env` — see [.env.example](.env.example). Generation goes through the `openai` SDK,
so point `LLM_BASE_URL` at any OpenAI-compatible endpoint (Ollama's `http://localhost:11434/v1`, a
hosted `https://api.openai.com/v1`, etc.), set `LLM_MODEL`, and `LLM_API_KEY` for hosted endpoints.
The prompt + ontology grounding are model-agnostic, so re-run `text2sparql eval` after a swap to
measure the change.

## Roadmap

- **Schema selection for very large ontologies.** Today the whole ontology is sent to the model,
  which is ideal while it fits in context. For endpoints with hundreds of classes / thousands of
  properties (DBpedia, Wikidata), a selection step in `_build_prompt` would pick the relevant slice
  — most naturally a lexical + graph-neighbourhood match (expand from question terms along property
  domain/range edges), with embeddings only as an optional fallback.
