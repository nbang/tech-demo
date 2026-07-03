"""Reproducible accuracy check: run gold questions end-to-end and compare results.

Why this exists: an LLM-backed tool can't be trusted to "look right" — a prompt tweak, a
data change, or a model swap can silently break a query that used to work. `eval` turns
accuracy into a number you can watch move.

Each case ships a GOLD SPARQL query rather than hardcoded answer values. For every case we
execute both the gold query and the model's generated query, then compare their result sets
— so the expected answer always reflects what the graph actually contains (execution accuracy).

Matching is intentionally lenient about *presentation* and strict about *content*: we collapse
each result table into a set of cell values and compare. A case passes when either
  (a) some single column of the model's result equals the gold value set, or
  (b) the flattened set of all the model's cells equals the gold set (covers e.g. "name + count").
Use match="subset" for open-ended questions where the gold values need only be present.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from . import engine, graph


@dataclass
class EvalCase:
    question: str
    sparql: str  # gold SPARQL query — executed to produce the expected result set
    graph: str
    match: str = "auto"  # "auto" | "subset"


@dataclass
class EvalOutcome:
    case: EvalCase
    passed: bool
    got: list[str]       # the model's result cells
    expected: list[str]  # the gold query's result cells
    sparql: str          # the model's generated query
    attempts: int
    error: str | None


def load_cases(path: str | Path) -> list[EvalCase]:
    cases: list[EvalCase] = []
    for raw in Path(path).read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        d = json.loads(line)
        cases.append(
            EvalCase(
                question=d["question"],
                sparql=d["sparql"],
                graph=d["graph"],
                match=d.get("match", "auto"),
            )
        )
    return cases


def _norm(v) -> str:
    return "" if v is None else str(v)


def _cells(result) -> list[str]:
    """Flatten a result table into its sorted set of distinct cell values."""
    if result is None:
        return []
    return sorted({_norm(v) for row in result.rows for v in row})


def _check(result, expect: list[str], mode: str) -> tuple[bool, list[str]]:
    want = {str(x) for x in expect}
    if result is None:
        return False, []
    all_cells = {_norm(v) for row in result.rows for v in row}
    if mode == "subset":
        return want <= all_cells, sorted(all_cells)
    # auto: any single column equals the expected set, or the flattened set does.
    col_sets = [
        {_norm(row[i]) for row in result.rows} for i in range(len(result.columns))
    ]
    passed = all_cells == want or any(cs == want for cs in col_sets)
    return passed, sorted(all_cells)


def run_eval(path: str | Path, skip_ingest: bool = False) -> list[EvalOutcome]:
    cases = load_cases(path)
    # Ingest each distinct graph once, reusing the index across its cases.
    graph_ids: dict[str, str] = {}
    for src in {c.graph for c in cases}:
        graph_ids[src] = engine._graph_id(src) if skip_ingest else engine.ingest(src).graph_id

    outcomes: list[EvalOutcome] = []
    for case in cases:
        # Never let one stalled/failed generation abort the whole suite — record it and move on.
        try:
            gold = graph.run_query(case.graph, case.sparql)
        except Exception as e:
            outcomes.append(
                EvalOutcome(case=case, passed=False, got=[], expected=[], sparql="",
                            attempts=0, error=f"gold query failed: {e}")
            )
            continue
        expected = _cells(gold)

        try:
            ans = engine.answer(case.question, graph_ids[case.graph])
        except Exception as e:
            outcomes.append(
                EvalOutcome(case=case, passed=False, got=[], expected=expected, sparql="",
                            attempts=0, error=str(e))
            )
            continue
        passed, got = _check(ans.result, expected, case.match)
        outcomes.append(
            EvalOutcome(
                case=case,
                passed=passed,
                got=got,
                expected=expected,
                sparql=ans.ask.sparql,
                attempts=ans.attempts,
                error=ans.error,
            )
        )
    return outcomes
