"""FastAPI app exposing ingest / ask / execute and serving the web UI."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import engine, llm
from .config import settings

app = FastAPI(title="text2sql", version="0.1.0")

_WEB = Path(__file__).resolve().parent.parent / "web"


class IngestRequest(BaseModel):
    connection_string: str
    name: str | None = None


class AskRequest(BaseModel):
    question: str
    db_id: str | None = None


class ExecuteRequest(BaseModel):
    sql: str
    db_id: str | None = None


@app.get("/")
def index() -> FileResponse:
    return FileResponse(_WEB / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "ollama_base_url": settings.ollama_base_url,
        "gen_model": settings.gen_model,
        "embed_model": settings.embed_model,
        "read_only": settings.read_only,
    }


@app.get("/api/databases")
def databases() -> dict:
    return {"databases": engine.list_databases()}


@app.post("/api/ingest")
def ingest(req: IngestRequest) -> dict:
    try:
        result = engine.ingest(req.connection_string, req.name)
    except (ValueError, llm.LLMError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # connection errors, etc.
        raise HTTPException(status_code=500, detail=f"Ingest failed: {e}")
    return {"db_id": result.db_id, "table_count": result.table_count, "tables": result.tables}


@app.post("/api/ask")
def ask(req: AskRequest) -> dict:
    try:
        result = engine.ask(req.question, req.db_id)
    except (ValueError, llm.LLMError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "sql": result.sql,
        "explanation": result.explanation,
        "tables_used": result.tables_used,
        "context_tables": result.context_tables,
    }


@app.post("/api/execute")
def execute(req: ExecuteRequest) -> dict:
    if not req.sql.strip():
        raise HTTPException(status_code=400, detail="Empty SQL.")
    try:
        result = engine.execute(req.sql, req.db_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Query failed: {e}")
    return {
        "columns": result.columns,
        "rows": result.rows,
        "rowcount": result.rowcount,
        "truncated": result.truncated,
    }
