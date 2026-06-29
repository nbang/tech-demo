# text2sql

Natural-language → SQL for **PostgreSQL**, powered entirely by a **self-hosted, open-source LLM** (via [Ollama](https://ollama.com)). Point it at a connection string; it introspects the live schema, builds a small **schema-RAG** index, and turns questions like *"Show me the person who has the most orders this month"* into SQL — and can run it for you.

```
                  ┌──────────────┐   DDL    ┌───────────────┐  embeddings  ┌──────────────┐
  connection ───▶ │  introspect  │ ───────▶ │  schema docs  │ ───────────▶ │ vector store │
   string         └──────────────┘          └───────────────┘   (Ollama)   └──────┬───────┘
                                                                                   │ retrieve top-k
  question ────────────────────────────────────────────────────────────────────▶ │
                                                                            ┌──────▼───────┐
                                                                            │  LLM (Ollama)│ ──▶ SQL ──▶ execute ──▶ rows
                                                                            └──────────────┘
```

Everything runs locally: no data or schema ever leaves your machine.

## Stack

- **Python** + **FastAPI** (web UI + JSON API) and a small CLI.
- **Ollama** for both generation (`qwen3.5:4b` by default) and embeddings (`nomic-embed-text`).
- **psycopg 3** for Postgres introspection & execution.
- A tiny **numpy** cosine-similarity vector store (no Chroma/FAISS needed — schemas are small).

## Setup

```bash
# 1. Self-hosted LLM
brew install ollama            # or see ollama.com
ollama serve &                 # start the daemon
ollama pull qwen3.5:4b         # SQL generation
ollama pull nomic-embed-text   # embeddings

# 2. This tool
cd text2sql
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env           # optional — tweak models / safety
```

## Usage — Web UI

```bash
text2sql serve                 # http://127.0.0.1:8000
```

1. Paste a connection string (`postgresql://user:pass@host:5432/db`) and **Ingest**.
2. Type a question, then **Generate SQL** or **Generate & Run**.
3. The SQL box is editable — tweak it and **Execute**.

## Usage — CLI

```bash
text2sql ingest "postgresql://user:pass@localhost:5432/shop"
text2sql ask "Show me the person who has the most orders this month"
text2sql run "Top 5 products by revenue last quarter"   # generate + execute
```

## API

| Method | Path             | Body                                   |
|--------|------------------|----------------------------------------|
| POST   | `/api/ingest`    | `{connection_string, name?}`           |
| POST   | `/api/ask`       | `{question, db_id?}` → `{sql, ...}`    |
| POST   | `/api/execute`   | `{sql, db_id?}` → `{columns, rows}`    |
| GET    | `/api/databases` | list ingested databases               |
| GET    | `/api/health`    | model / config info                    |

## Safety

By design this tool **executes whatever SQL is generated, including writes** (your chosen mode).
Point it at a database you're comfortable mutating, or flip it to read-only:

```bash
TEXT2SQL_READONLY=1 text2sql serve   # wraps every query in a READ ONLY transaction
```

Ingest persists the connection string (credentials included) under `.text2sql/registry.json`
so `ask`/`execute` work across restarts. That directory is git-ignored — keep it private, or
clear it when done.

## Configuration

All via env / `.env` — see [.env.example](.env.example). Swap models freely, e.g.
`TEXT2SQL_GEN_MODEL=qwen2.5-coder:7b` or any Ollama model.
