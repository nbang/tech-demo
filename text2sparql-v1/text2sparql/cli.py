"""Command-line entrypoint: ingest a graph, ask for SPARQL, exec raw SPARQL, or eval."""

from __future__ import annotations

import argparse
import sys

from . import engine, graph


def _print_result(result) -> None:
    if not result.columns:
        print(f"OK — {result.rowcount} row(s).")
        return
    print(" | ".join(result.columns))
    print("-" * 60)
    for row in result.rows:
        print(" | ".join("" if v is None else str(v) for v in row))
    if result.truncated:
        print(f"... (truncated to {graph.MAX_ROWS} rows)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="text2sparql", description="NL→SPARQL for RDF graphs via a self-hosted LLM.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ing = sub.add_parser("ingest", help="Introspect an RDF file or SPARQL endpoint and build its ontology-RAG index.")
    p_ing.add_argument("source", help="Path to an RDF file (.ttl/.rdf/.nt/.jsonld) or a SPARQL endpoint URL.")
    p_ing.add_argument("--name")
    p_ing.add_argument("--quiet", action="store_true",
                       help="Only print the summary line; don't show the captured ontology.")

    p_ask = sub.add_parser("ask", help="Generate SPARQL for a question and print only the query (does not execute).")
    p_ask.add_argument("question")
    p_ask.add_argument("--graph-id")

    p_exec = sub.add_parser("exec", help="Execute a raw SPARQL query directly (read-only).")
    p_exec.add_argument("sparql", help="The SPARQL query to execute.")
    p_exec.add_argument("--graph-id")

    p_eval = sub.add_parser("eval", help="Run gold questions from a JSONL file and report accuracy.")
    p_eval.add_argument("path", nargs="?", default="examples/eval.jsonl",
                        help="JSONL of {graph, question, expect[, match]} cases (default: examples/eval.jsonl).")
    p_eval.add_argument("--skip-ingest", action="store_true",
                        help="Reuse the existing index for each graph instead of re-ingesting.")

    args = parser.parse_args(argv)

    if args.cmd == "ingest":
        res = engine.ingest(args.source, args.name)
        print(f"Ingested graph_id={res.graph_id} (name={res.name}) with {res.class_count} classes.")
        if not args.quiet:
            print(f"\nPrefixes ({len(res.prefixes)}):")
            for pfx, ns in sorted(res.prefixes.items()):
                print(f"  {pfx}: <{ns}>")
            print("\nOntology captured (this is the context handed to the model):")
            print("=" * 60)
            for doc in res.documents:
                print(doc)
                print("-" * 60)
        return 0

    if args.cmd == "ask":
        print(engine.ask(args.question, args.graph_id))
        return 0

    if args.cmd == "exec":
        try:
            _print_result(engine.execute(args.sparql, args.graph_id))
        except ValueError as e:
            print(f"Error: {e}")
            return 1
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
                print(f"       expected: {o.expected}")
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
