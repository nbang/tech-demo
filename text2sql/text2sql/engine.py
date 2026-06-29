"""Core engine: ingest a database into a schema-RAG index, then answer questions as SQL."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from . import db, llm
from .config import settings
from .vectorstore import VectorStore

_REGISTRY = settings.data_dir / "registry.json"

SYSTEM_PROMPT = """You are an expert PostgreSQL analyst. Convert the user's question into ONE valid PostgreSQL query.

Rules:
- Use ONLY the tables and columns in the provided schema. Never invent names.
- Join tables using the documented foreign keys.
- For relative dates ("this month", "today", "last quarter"), use CURRENT_DATE / date_trunc / NOW() — never hardcode dates.
- Add a LIMIT when the question implies a list.
- If a value is not a column (e.g. revenue), derive it from existing columns.

Reply with a JSON object only:
{"sql": "<the query>", "explanation": "<one sentence>", "tables_used": ["schema.table", ...]}"""


def _user_prompt(question: str, ddl_context: str) -> str:
    return (
        "Database schema (PostgreSQL DDL):\n"
        f"{ddl_context}\n\n"
        f"Question: {question}"
    )


def _db_id(connection_string: str) -> str:
    return hashlib.sha1(connection_string.encode()).hexdigest()[:12]


def _read_registry() -> dict:
    if _REGISTRY.exists():
        return json.loads(_REGISTRY.read_text())
    return {}


def _write_registry(reg: dict) -> None:
    _REGISTRY.write_text(json.dumps(reg, indent=2))


@dataclass
class IngestResult:
    db_id: str
    table_count: int
    tables: list[str]


def ingest(connection_string: str, name: str | None = None) -> IngestResult:
    """Introspect the database, embed each table's description, and persist the index."""
    tables = db.introspect(connection_string)
    if not tables:
        raise ValueError("No base tables found in this database (check the connection string / search_path).")

    ids = [t.qualified for t in tables]
    # Store DDL: it embeds well (column names + inline comments carry the semantics)
    # and is exactly the context format text-to-SQL models expect at generation time.
    documents = [t.to_ddl() for t in tables]
    vectors = [llm.embed(doc) for doc in documents]

    db_id = _db_id(connection_string)
    store = VectorStore.build(ids, documents, vectors)
    store.save(settings.data_dir / db_id)

    reg = _read_registry()
    reg[db_id] = {
        "name": name or _db_id(connection_string),
        "connection_string": connection_string,
        "table_count": len(tables),
        "tables": ids,
    }
    reg["_latest"] = db_id
    _write_registry(reg)

    return IngestResult(db_id=db_id, table_count=len(tables), tables=ids)


def list_databases() -> list[dict]:
    reg = _read_registry()
    out = []
    for db_id, meta in reg.items():
        if db_id.startswith("_"):
            continue
        out.append({"db_id": db_id, "name": meta["name"], "table_count": meta["table_count"]})
    return out


def _resolve(db_id: str | None) -> tuple[str, dict]:
    reg = _read_registry()
    if db_id is None:
        db_id = reg.get("_latest")
    if not db_id or db_id not in reg:
        raise ValueError("No ingested database found. Run /ingest first.")
    return db_id, reg[db_id]


@dataclass
class AskResult:
    sql: str
    explanation: str
    tables_used: list[str]
    context_tables: list[str]


def ask(question: str, db_id: str | None = None) -> AskResult:
    """Retrieve the most relevant tables, then ask the LLM to produce SQL."""
    db_id, meta = _resolve(db_id)
    store = VectorStore.load(settings.data_dir / db_id)

    hits = store.search(llm.embed(question), settings.top_k)
    context = "\n\n".join(doc for _, doc, _ in hits)

    data = llm.generate_sql(SYSTEM_PROMPT, _user_prompt(question, context))
    return AskResult(
        sql=(data.get("sql") or "").strip(),
        explanation=data.get("explanation", ""),
        tables_used=data.get("tables_used", []),
        context_tables=[i for i, _, _ in hits],
    )


def execute(sql: str, db_id: str | None = None) -> db.QueryResult:
    _, meta = _resolve(db_id)
    return db.run_query(meta["connection_string"], sql)
