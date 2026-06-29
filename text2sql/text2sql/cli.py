"""Command-line entrypoint: ingest, ask, run a question end-to-end, or start the server."""

from __future__ import annotations

import argparse
import json
import sys

from . import engine
from .config import settings


def _print_result(result) -> None:
    if not result.columns:
        print(f"OK — {result.rowcount} row(s) affected.")
        return
    print(" | ".join(result.columns))
    print("-" * 60)
    for row in result.rows:
        print(" | ".join("" if v is None else str(v) for v in row))
    if result.truncated:
        print(f"... (truncated to {settings.max_rows} rows)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="text2sql", description="NL→SQL for Postgres via a self-hosted LLM.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ing = sub.add_parser("ingest", help="Introspect a database and build its schema-RAG index.")
    p_ing.add_argument("connection_string")
    p_ing.add_argument("--name")

    p_ask = sub.add_parser("ask", help="Generate SQL for a question (does not execute).")
    p_ask.add_argument("question")
    p_ask.add_argument("--db-id")

    p_run = sub.add_parser("run", help="Generate SQL and execute it, printing the result.")
    p_run.add_argument("question")
    p_run.add_argument("--db-id")

    p_srv = sub.add_parser("serve", help="Start the web UI / API server.")
    p_srv.add_argument("--host", default="127.0.0.1")
    p_srv.add_argument("--port", type=int, default=8000)

    args = parser.parse_args(argv)

    if args.cmd == "ingest":
        res = engine.ingest(args.connection_string, args.name)
        print(f"Ingested db_id={res.db_id} with {res.table_count} tables.")
        return 0

    if args.cmd == "ask":
        res = engine.ask(args.question, args.db_id)
        print(json.dumps({"sql": res.sql, "explanation": res.explanation, "tables_used": res.tables_used}, indent=2))
        return 0

    if args.cmd == "run":
        res = engine.ask(args.question, args.db_id)
        print(f"-- {res.explanation}\n{res.sql}\n")
        if not res.sql:
            return 1
        _print_result(engine.execute(res.sql, args.db_id))
        return 0

    if args.cmd == "serve":
        import uvicorn

        uvicorn.run("text2sql.api:app", host=args.host, port=args.port)
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
