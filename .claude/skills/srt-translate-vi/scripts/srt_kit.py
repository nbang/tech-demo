#!/usr/bin/env python3
"""SubRip (.srt) toolkit: split a subtitle file into translation batches, merge
translations back, and validate the result.

The point of this module is that timecodes are never re-generated. `split` hands
out text only; `merge` copies the index and timing lines from the source file
byte-for-byte and drops translated text in between. A translator (human, Claude,
or an LLM endpoint) therefore cannot desynchronise the subtitles.

Subcommands
  split <in.srt> --work DIR        write batch_NNN.json holding text + length budgets
  merge <in.srt> --work DIR -o OUT rebuild an .srt from batch_NNN.vi.json files
  check <out.srt> [--against SRC]  structural + readability report
  stats <in.srt>                   cue count, duration, language guess
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

# Subtitle readability budgets. Vietnamese runs roughly 15-25% longer than
# English and much longer than Chinese, so the length budget handed to the
# translator matters more than usual.
CPS_COMFORT = 17.0  # chars/second used to compute each cue's char budget
CPS_MAX = 21.0      # above this a cue is hard to read; reported as a warning
MAX_LINE = 42       # chars per line
MAX_LINES = 2

TIMING_RE = re.compile(
    r"(?P<start>\d{1,3}:\d{1,2}:\d{1,2}[,.]\d{1,3})"
    r"\s*-->\s*"
    r"(?P<end>\d{1,3}:\d{1,2}:\d{1,2}[,.]\d{1,3})"
)

# Markup that must survive translation untouched.
TAG_RE = re.compile(r"</?[a-zA-Z][^>]*>|\{\\[^}]*\}")


@dataclass
class Cue:
    number: int      # 1-based position in the file; the stable id used everywhere
    raw_index: str   # index line exactly as written ("" if the file omitted it)
    timing: str      # full timing line, verbatim
    lines: list[str]

    @property
    def text(self) -> str:
        return "\n".join(self.lines)

    @property
    def start(self) -> str:
        m = TIMING_RE.search(self.timing)
        return m.group("start") if m else ""

    @property
    def end(self) -> str:
        m = TIMING_RE.search(self.timing)
        return m.group("end") if m else ""

    @property
    def duration(self) -> float:
        m = TIMING_RE.search(self.timing)
        if not m:
            return 0.0
        return max(0.0, tc_seconds(m.group("end")) - tc_seconds(m.group("start")))

    @property
    def char_budget(self) -> int:
        """Soft cap on translated length so the cue stays readable."""
        return max(20, min(MAX_LINE * MAX_LINES, round(self.duration * CPS_COMFORT)))


def tc_seconds(tc: str) -> float:
    h, m, rest = tc.split(":")
    s, ms = re.split(r"[,.]", rest)
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000.0


# --------------------------------------------------------------------------- IO


def read_text(path: Path) -> tuple[str, str, str]:
    """Decode an .srt file. Returns (text, encoding, newline).

    Subtitle files in the wild are UTF-8, UTF-8 with BOM, or — for Chinese —
    GB18030/Big5. latin-1 is the never-fails fallback so we degrade to mojibake
    rather than crashing.
    """
    data = path.read_bytes()
    candidates = ["utf-8-sig", "utf-8"]
    try:  # optional dependency; skipped silently when absent
        import chardet  # type: ignore

        guess = chardet.detect(data).get("encoding")
        if guess:
            candidates.append(guess)
    except Exception:
        pass
    candidates += ["gb18030", "big5", "cp1252", "latin-1"]

    for enc in candidates:
        try:
            text = data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
        newline = "\r\n" if b"\r\n" in data else "\n"
        return text, enc, newline
    raise SystemExit(f"could not decode {path}")


def parse(text: str) -> tuple[list[Cue], list[str]]:
    """Parse SRT text into cues. Returns (cues, warnings)."""
    text = text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    warnings: list[str] = []
    cues: list[Cue] = []

    for block in re.split(r"\n[ \t]*\n+", text.strip()):
        lines = block.split("\n")
        ti = next((i for i, ln in enumerate(lines) if TIMING_RE.search(ln)), None)
        if ti is None:
            snippet = block.strip().replace("\n", " / ")[:60]
            if snippet:
                warnings.append(f"block without a timing line, skipped: {snippet!r}")
            continue
        body = [ln for ln in lines[ti + 1:]]
        while body and not body[-1].strip():
            body.pop()
        cues.append(
            Cue(
                number=len(cues) + 1,
                raw_index=lines[ti - 1].strip() if ti > 0 else "",
                timing=lines[ti].strip(),
                lines=body,
            )
        )

    for cue in cues:
        if not cue.lines:
            warnings.append(f"cue {cue.number} ({cue.start}) has no text")
    return cues, warnings


def load_srt(path: Path) -> tuple[list[Cue], str, str, list[str]]:
    text, enc, newline = read_text(path)
    cues, warnings = parse(text)
    if not cues:
        raise SystemExit(f"no subtitle cues found in {path}")
    return cues, enc, newline, warnings


def render(cues: list[Cue], newline: str = "\n") -> str:
    blocks = []
    for cue in cues:
        index = cue.raw_index or str(cue.number)
        blocks.append("\n".join([index, cue.timing, *cue.lines]))
    out = "\n\n".join(blocks) + "\n"
    return out.replace("\n", newline) if newline != "\n" else out


# ------------------------------------------------------------------- languages


VI_MARKERS = set("ăâđêôơưĂÂĐÊÔƠƯ")


def guess_language(cues: list[Cue]) -> str:
    sample = "".join(c.text for c in cues[:200])
    han = sum(1 for ch in sample if "一" <= ch <= "鿿")
    latin = sum(1 for ch in sample if ch.isascii() and ch.isalpha())
    if han > max(10, latin * 0.2):
        return "zh"
    # Vietnamese shares the Latin alphabet with English, so key off the letters
    # only Vietnamese has. Matters for reporting on output files.
    if sum(1 for ch in sample if ch in VI_MARKERS) > max(2, len(sample) * 0.005):
        return "vi"
    if latin:
        return "en"
    return "unknown"


def display_width(s: str) -> int:
    """Count CJK wide chars as 2 columns so line-length checks mean something."""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in s)


# ----------------------------------------------------------------- subcommands


def cmd_split(args: argparse.Namespace) -> int:
    src = Path(args.input)
    cues, enc, newline, warnings = load_srt(src)
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    for stale in work.glob("batch_*.json"):
        stale.unlink()

    # Group cues into batches bounded by both cue count and character count, so
    # a batch of long monologues does not blow past a sensible request size.
    batches: list[list[Cue]] = []
    current: list[Cue] = []
    chars = 0
    for cue in cues:
        if current and (len(current) >= args.batch_size or chars + len(cue.text) > args.max_chars):
            batches.append(current)
            current, chars = [], 0
        current.append(cue)
        chars += len(cue.text)
    if current:
        batches.append(current)

    lang = args.source if args.source != "auto" else guess_language(cues)
    manifest = {
        "source_file": str(src),
        "encoding": enc,
        "newline": "crlf" if newline == "\r\n" else "lf",
        "cue_count": len(cues),
        "source_language": lang,
        "target_language": "vi",
        "total_batches": len(batches),
        "batches": [],
        "warnings": warnings,
    }

    for i, batch in enumerate(batches, start=1):
        context = cues[batch[0].number - 1 - args.context: batch[0].number - 1]
        payload = {
            "batch": i,
            "total_batches": len(batches),
            "source_language": lang,
            "target_language": "vi",
            "context_before": [{"id": c.number, "text": c.text} for c in context],
            "cues": [
                {
                    "id": c.number,
                    "start": c.start,
                    "end": c.end,
                    "duration": round(c.duration, 2),
                    "max_chars": c.char_budget,
                    "text": c.text,
                }
                for c in batch
            ],
        }
        out = work / f"batch_{i:03d}.json"
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest["batches"].append({"file": out.name, "ids": [c.number for c in batch]})

    (work / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"{len(cues)} cues, detected source language: {lang}, encoding: {enc}")
    print(f"wrote {len(batches)} batch file(s) to {work}/")
    for w in warnings:
        print(f"  warning: {w}", file=sys.stderr)
    return 0


def cmd_merge(args: argparse.Namespace) -> int:
    src = Path(args.input)
    cues, _enc, newline, _warnings = load_srt(src)
    work = Path(args.work)

    translations: dict[int, str] = {}
    files = sorted(work.glob("batch_*.vi.json"))
    if not files:
        raise SystemExit(f"no batch_*.vi.json files in {work}/ — nothing to merge")
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        items = data.get("translations", data)
        if not isinstance(items, dict):
            raise SystemExit(f"{f}: expected an object of id -> translated text")
        for key, value in items.items():
            try:
                cid = int(key)
            except (TypeError, ValueError):
                raise SystemExit(f"{f}: cue id {key!r} is not an integer")
            if not isinstance(value, str):
                raise SystemExit(f"{f}: translation for cue {cid} is not a string")
            translations[cid] = value

    missing = [c.number for c in cues if c.number not in translations]
    extra = sorted(set(translations) - {c.number for c in cues})
    if extra:
        raise SystemExit(f"translations reference unknown cue ids: {extra[:20]}")
    if missing and not args.allow_missing:
        preview = ", ".join(map(str, missing[:20]))
        more = f" (+{len(missing) - 20} more)" if len(missing) > 20 else ""
        raise SystemExit(
            f"{len(missing)} cue(s) have no translation: {preview}{more}\n"
            "Translate them, or pass --allow-missing to keep the source text."
        )

    blank = []
    out_cues: list[Cue] = []
    for cue in cues:
        vi = translations.get(cue.number)
        if vi is None or not vi.strip():
            if vi is not None:
                blank.append(cue.number)
            body = cue.lines
        else:
            body = vi.replace("\r\n", "\n").split("\n")
        if args.bilingual and cue.lines:
            body = [*body, *cue.lines]
        out_cues.append(Cue(cue.number, cue.raw_index, cue.timing, body))

    text = render(out_cues, newline)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8-sig" if args.bom else "utf-8", newline="")

    print(f"wrote {out_path} ({len(out_cues)} cues, timings copied from {src.name})")
    if missing:
        print(f"  {len(missing)} cue(s) kept the source text: {missing[:20]}", file=sys.stderr)
    if blank:
        print(f"  {len(blank)} cue(s) had an empty translation: {blank[:20]}", file=sys.stderr)
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    cues, enc, _newline, warnings = load_srt(Path(args.input))
    problems: list[str] = list(warnings)

    if args.against:
        src, _e, _n, _w = load_srt(Path(args.against))
        if len(src) != len(cues):
            problems.append(f"cue count differs: source {len(src)} vs output {len(cues)}")
        for a, b in zip(src, cues):
            if a.timing != b.timing:
                problems.append(
                    f"cue {a.number}: timing changed — source {a.timing!r}, output {b.timing!r}"
                )
            if a.raw_index != b.raw_index:
                problems.append(f"cue {a.number}: index line changed")
            src_tags = TAG_RE.findall(a.text)
            out_tags = TAG_RE.findall(b.text)
            if sorted(src_tags) != sorted(out_tags):
                problems.append(f"cue {a.number}: markup differs {src_tags} -> {out_tags}")

    long_lines, too_many_lines, fast = [], [], []
    for cue in cues:
        for ln in cue.lines:
            if display_width(TAG_RE.sub("", ln)) > MAX_LINE:
                long_lines.append(cue.number)
                break
        if len(cue.lines) > MAX_LINES:
            too_many_lines.append(cue.number)
        plain = TAG_RE.sub("", cue.text.replace("\n", " "))
        if cue.duration > 0 and len(plain) / cue.duration > CPS_MAX:
            fast.append(cue.number)

    print(f"{args.input}: {len(cues)} cues, encoding {enc}, language guess {guess_language(cues)}")
    if problems:
        print(f"\nSTRUCTURAL PROBLEMS ({len(problems)}):")
        for p in problems[:40]:
            print(f"  - {p}")
        if len(problems) > 40:
            print(f"  ... {len(problems) - 40} more")
    else:
        print("structure: OK (timings, indices and markup match)" if args.against else "structure: OK")

    def report(label: str, ids: list[int]) -> None:
        if ids:
            shown = ", ".join(map(str, ids[:15]))
            more = f" ... +{len(ids) - 15}" if len(ids) > 15 else ""
            print(f"readability: {len(ids)} cue(s) {label}: {shown}{more}")

    report(f"exceed {MAX_LINE} chars on a line", long_lines)
    report(f"have more than {MAX_LINES} lines", too_many_lines)
    report(f"read faster than {CPS_MAX:.0f} chars/sec", fast)
    if not (long_lines or too_many_lines or fast):
        print("readability: OK")

    return 1 if problems else 0


def cmd_stats(args: argparse.Namespace) -> int:
    cues, enc, newline, warnings = load_srt(Path(args.input))
    total_chars = sum(len(c.text) for c in cues)
    span = tc_seconds(cues[-1].end) if cues[-1].end else 0.0
    print(f"file          : {args.input}")
    print(f"encoding      : {enc}  newline: {'CRLF' if newline == chr(13) + chr(10) else 'LF'}")
    print(f"cues          : {len(cues)}")
    print(f"characters    : {total_chars}")
    print(f"runtime       : {span / 60:.1f} min")
    print(f"language guess: {guess_language(cues)}")
    for w in warnings:
        print(f"warning       : {w}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("split", help="write translation batches")
    p.add_argument("input")
    p.add_argument("--work", required=True, help="directory for batch files")
    p.add_argument("--batch-size", type=int, default=40, help="max cues per batch (default 40)")
    p.add_argument("--max-chars", type=int, default=3500, help="max source chars per batch")
    p.add_argument("--context", type=int, default=3, help="preceding cues included as context")
    p.add_argument("--source", default="auto", choices=["auto", "en", "zh"])
    p.set_defaults(func=cmd_split)

    p = sub.add_parser("merge", help="rebuild an .srt from translated batches")
    p.add_argument("input", help="the ORIGINAL .srt (source of timings)")
    p.add_argument("--work", required=True)
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--bilingual", action="store_true", help="keep the source text below the translation")
    p.add_argument("--bom", action="store_true", help="write UTF-8 with BOM")
    p.add_argument("--allow-missing", action="store_true", help="keep source text for untranslated cues")
    p.set_defaults(func=cmd_merge)

    p = sub.add_parser("check", help="validate an .srt")
    p.add_argument("input")
    p.add_argument("--against", help="original .srt to compare timings against")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("stats", help="summarise an .srt")
    p.add_argument("input")
    p.set_defaults(func=cmd_stats)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
