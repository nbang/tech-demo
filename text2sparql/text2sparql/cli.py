"""Command-line entrypoint: ingest, ask, run a question end-to-end, or eval accuracy."""

from __future__ import annotations

import argparse
import json
import sys

from . import engine
from .config import settings


def _print_result(result) -> None:
    if not result.columns:
        print(f"OK — {result.rowcount} row(s).")
        return
    print(" | ".join(result.columns))
    print("-" * 60)
    for row in result.rows:
        print(" | ".join("" if v is None else str(v) for v in row))
    if result.truncated:
        print(f"... (truncated to {settings.max_rows} rows)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="text2sparql", description="NL→SPARQL for RDF graphs via a self-hosted LLM.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ing = sub.add_parser("ingest", help="Introspect an RDF file or SPARQL endpoint and build its ontology-RAG index.")
    p_ing.add_argument("source", help="Path to an RDF file (.ttl/.rdf/.nt/.jsonld) or a SPARQL endpoint URL.")
    p_ing.add_argument("--name")

    p_ask = sub.add_parser("ask", help="Generate SPARQL for a question (does not execute).")
    p_ask.add_argument("question")
    p_ask.add_argument("--graph-id")

    p_run = sub.add_parser("run", help="Generate SPARQL and execute it, printing the result.")
    p_run.add_argument("question")
    p_run.add_argument("--graph-id")

    p_eval = sub.add_parser("eval", help="Run gold questions from a JSONL file and report accuracy.")
    p_eval.add_argument("path", nargs="?", default="examples/eval.jsonl",
                        help="JSONL of {graph, question, expect[, match]} cases (default: examples/eval.jsonl).")
    p_eval.add_argument("--skip-ingest", action="store_true",
                        help="Reuse the existing index for each graph instead of re-ingesting.")

    args = parser.parse_args(argv)

    if args.cmd == "ingest":
        res = engine.ingest(args.source, args.name)
        print(f"Ingested graph_id={res.graph_id} with {res.class_count} classes.")
        return 0

    if args.cmd == "ask":
        res = engine.ask(args.question, args.graph_id)
        print(json.dumps({"sparql": res.sparql, "explanation": res.explanation, "classes_used": res.classes_used}, indent=2))
        return 0

    if args.cmd == "run":
        ans = engine.answer(args.question, args.graph_id)
        if ans.attempts > 1:
            print(f"# (self-repaired over {ans.attempts} attempts)")
        print(f"# {ans.ask.explanation}\n{ans.ask.sparql}\n")
        if ans.error:
            print(f"Could not produce a working query: {ans.error}")
            return 1
        if ans.result is not None:
            _print_result(ans.result)
        return 0

    if args.cmd == "eval":
        from . import eval as evalmod

        outcomes = evalmod.run_eval(args.path, skip_ingest=args.skip_ingest)
        passed = 0
        for o in outcomes:
            mark = "PASS" if o.passed else "FAIL"
            if o.passed:
                passed += 1
            note = f" (repaired ×{o.attempts})" if o.attempts > 1 else ""
            print(f"[{mark}]{note} {o.case.question}")
            if not o.passed:
                print(f"       expected: {sorted(set(o.case.expect))}")
                print(f"       got:      {o.got}")
                if o.error:
                    print(f"       error:    {o.error}")
                print(f"       sparql:   {o.sparql.splitlines()[0] if o.sparql else '(empty)'} ...")
        total = len(outcomes)
        pct = (100 * passed / total) if total else 0.0
        print("-" * 60)
        print(f"Accuracy: {passed}/{total} ({pct:.0f}%)")
        return 0 if passed == total else 1

    return 1


if __name__ == "__main__":
    sys.exit(main())
