"""Reproducible accuracy check: run gold questions end-to-end and compare results.

Why this exists: an LLM-backed tool can't be trusted to "look right" — a prompt tweak, a
data change, or a model swap can silently break a query that used to work. `eval` turns
accuracy into a number you can watch move.

Matching is intentionally lenient about *presentation* and strict about *content*: we collapse
the whole result table into a set of cell values and compare that to the expected answer set,
so row order and column naming never matter. A case passes when either
  (a) some single result column's distinct values equal the expected set, or
  (b) the flattened set of all cells equals the expected set (covers e.g. "name + count" rows).
Use match="subset" for open-ended questions where the expected values need only be present.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from . import engine


@dataclass
class EvalCase:
    question: str
    expect: list[str]
    graph: str
    match: str = "auto"  # "auto" | "subset"


@dataclass
class EvalOutcome:
    case: EvalCase
    passed: bool
    got: list[str]
    sparql: str
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
                expect=[str(x) for x in d["expect"]],
                graph=d["graph"],
                match=d.get("match", "auto"),
            )
        )
    return cases


def _norm(v) -> str:
    return "" if v is None else str(v)


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
            ans = engine.answer(case.question, graph_ids[case.graph])
        except Exception as e:
            outcomes.append(
                EvalOutcome(case=case, passed=False, got=[], sparql="", attempts=0, error=str(e))
            )
            continue
        passed, got = _check(ans.result, case.expect, case.match)
        outcomes.append(
            EvalOutcome(
                case=case,
                passed=passed,
                got=got,
                sparql=ans.ask.sparql,
                attempts=ans.attempts,
                error=ans.error,
            )
        )
    return outcomes
