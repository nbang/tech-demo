#!/usr/bin/env python3
"""Translate an English or Chinese .srt into Vietnamese via an OpenAI-compatible
chat-completions endpoint, keeping every timecode byte-identical.

Only srt_kit.py and the standard library are required — no SDK, no extra deps.

    export SRT_API_KEY=nvapi-...         # omit for local servers that don't check
    python3 translate_srt.py movie.en.srt -o movie.vi.srt

Defaults target NVIDIA's hosted deepseek-ai/deepseek-v4-flash. Override with
SRT_API_BASE / SRT_MODEL (or --base-url / --model) for any other endpoint —
anything OpenAI-compatible works, local servers included.

One request per batch: the full rule set goes in the system prompt and JSON keyed
by cue id comes back. Parsing, batching and re-assembly all go through srt_kit,
so the model only ever sees and returns text keyed by cue id; it cannot touch the
timings.
"""

from __future__ import annotations

import argparse
import concurrent.futures as futures
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import srt_kit  # noqa: E402

DEFAULT_BASE = "https://integrate.api.nvidia.com/v1"
DEFAULT_MODEL = "deepseek-ai/deepseek-v4-flash"

LANG_NAMES = {"en": "English", "zh": "Chinese", "unknown": "the source language"}

API_ERRORS = (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError,
              KeyError, json.JSONDecodeError)

SYSTEM_PROMPT = """You are a professional subtitle translator working into Vietnamese (Tiếng Việt).

Rules:
1. Translate the meaning, not the words. Produce natural spoken Vietnamese that a viewer reads at a glance.
2. Return EXACTLY one translation per input cue id. Never merge, split, drop or reorder cues.
3. Respect each cue's max_chars budget. Prefer 1 line; use at most 2 lines separated by a single \\n.
4. Preserve markup verbatim: HTML tags such as <i>, <b>, <font ...> and ASS overrides such as {\\an8}.
5. Keep proper nouns, numbers, units and on-screen text conventions. Do not romanise Chinese names into pinyin when a Vietnamese-Sino reading is customary in subtitles.
6. Use the correct pronouns and register for the relationship between speakers, and keep them consistent across cues.
7. A cue that is only music notes, sound effects, or blank stays as-is (translate bracketed sound descriptions).
8. Never add notes, explanations, romanisation or commentary.

Reply with JSON only: an object mapping each cue id (as a string) to its Vietnamese text."""


def build_user_prompt(batch: dict, glossary: dict[str, str]) -> str:
    src = LANG_NAMES.get(batch.get("source_language", "unknown"), "the source language")
    parts = [
        f"Translate these subtitle cues from {src} into Vietnamese.",
        f"Batch {batch['batch']} of {batch['total_batches']}.",
    ]
    if glossary:
        lines = "\n".join(f"  {k} -> {v}" for k, v in glossary.items())
        parts.append(f"Use this glossary exactly:\n{lines}")
    if batch.get("context_before"):
        ctx = "\n".join(f"  [{c['id']}] {c['text']}" for c in batch["context_before"])
        parts.append(f"Preceding cues, for context only — do NOT translate these:\n{ctx}")
    cues = [
        {"id": c["id"], "max_chars": c["max_chars"], "text": c["text"]}
        for c in batch["cues"]
    ]
    ids = [c["id"] for c in cues]
    parts.append("Cues to translate:\n" + json.dumps(cues, ensure_ascii=False, indent=1))
    parts.append(
        f"Return a JSON object with exactly these {len(ids)} keys: "
        f"{json.dumps([str(i) for i in ids])}"
    )
    return "\n\n".join(parts)


def post_chat(base: str, key: str, model: str, messages: list[dict], temperature: float,
              timeout: int) -> str:
    body = json.dumps(
        {"model": model, "messages": messages, "temperature": temperature,
         "response_format": {"type": "json_object"}},
        ensure_ascii=False,
    ).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(
        base.rstrip("/") + "/chat/completions", data=body, headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload["choices"][0]["message"]["content"]


# NVIDIA's hosted endpoints return 529 "Service temporarily overloaded" whenever a
# model is contended — measured at roughly a 1-in-3 success rate on deepseek-v4-flash.
# That is capacity contention, not rate limiting, so the win is *more attempts* on a
# gentle ramp rather than long exponential waits that burn the retry budget on sleep.
OVERLOAD_CODES = {429, 500, 502, 503, 529}


def retry_delay(exc: BaseException | None, attempt: int) -> float:
    if isinstance(exc, urllib.error.HTTPError):
        after = exc.headers.get("Retry-After") if exc.headers else None
        if after:
            try:
                return min(float(after), 60.0)
            except ValueError:
                pass
        if exc.code in OVERLOAD_CODES:
            return min(3.0 * attempt, 15.0)
    return min(2 ** attempt, 15)


def extract_json(raw: str) -> dict:
    """Models wrap JSON in prose or fences often enough to be worth handling."""
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start:end + 1])
    raise ValueError(f"no JSON object in model reply: {raw[:200]!r}")


def translate_batch(batch: dict, cfg: argparse.Namespace, glossary: dict[str, str]) -> dict[str, str]:
    want = {str(c["id"]) for c in batch["cues"]}
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(batch, glossary)},
    ]
    last_error = ""
    last_exc: BaseException | None = None

    for attempt in range(1, cfg.retries + 1):
        try:
            raw = post_chat(cfg.base_url, cfg.api_key, cfg.model, messages,
                            cfg.temperature, cfg.timeout)
            data = extract_json(raw)
            out = {k: v for k, v in data.items() if isinstance(v, str)}
            missing = sorted(want - set(out), key=int)
            if not missing:
                return {k: out[k] for k in want}
            last_error, last_exc = f"missing cue ids {missing[:10]}", None
            # Ask for just the gap rather than redoing the whole batch.
            messages += [
                {"role": "assistant", "content": raw},
                {"role": "user", "content":
                    "Your reply is missing these cue ids: "
                    f"{json.dumps(missing)}. Reply with JSON containing ONLY those keys."},
            ]
        except API_ERRORS as exc:
            last_error, last_exc = f"{type(exc).__name__}: {exc}", exc

        if attempt < cfg.retries:
            delay = retry_delay(last_exc, attempt)
            print(f"  batch {batch['batch']}: {last_error} — retrying in {delay:.0f}s "
                  f"({attempt}/{cfg.retries - 1})", file=sys.stderr)
            time.sleep(delay)

    raise RuntimeError(f"batch {batch['batch']} failed after {cfg.retries} attempt(s): {last_error}")


def load_dotenv() -> None:
    """Read KEY=VALUE from the skill's .env, then ./.env — same convention as the
    sibling projects in this repo. Real environment variables always win."""
    for path in (Path(__file__).resolve().parent.parent / ".env", Path(".env")):
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def load_glossary(path: str | None) -> dict[str, str]:
    if not path:
        return {}
    out: dict[str, str] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = re.split(r"\t|=>|\|", line, maxsplit=1)
        if len(parts) == 2:
            out[parts[0].strip()] = parts[1].strip()
    return out


def main() -> int:
    load_dotenv()  # before the parser reads its os.environ defaults
    ap = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="source .srt (English or Chinese)")
    ap.add_argument("-o", "--output", help="output .srt (default: <input>.vi.srt)")
    ap.add_argument("--base-url", default=os.environ.get("SRT_API_BASE", DEFAULT_BASE))
    ap.add_argument("--api-key", default=os.environ.get("SRT_API_KEY", ""))
    ap.add_argument("--model", default=os.environ.get("SRT_MODEL", DEFAULT_MODEL))
    ap.add_argument("--source", default="auto", choices=["auto", "en", "zh"])
    ap.add_argument("--batch-size", type=int, default=25)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--retries", type=int, default=8,
                    help="attempts per batch; hosted models 529 often, so keep this high")
    ap.add_argument("--glossary", help="TSV of source<TAB>vietnamese term pairs")
    ap.add_argument("--work", help="keep batch files in this directory")
    ap.add_argument("--bilingual", action="store_true", help="keep source text under the translation")
    ap.add_argument("--bom", action="store_true")
    ap.add_argument("--allow-partial", action="store_true",
                    help="keep source text for batches that fail instead of aborting")
    args = ap.parse_args()

    if not args.model:
        ap.error("no model given — pass --model or set SRT_MODEL")

    src = Path(args.input)
    out_path = Path(args.output) if args.output else src.with_suffix(".vi.srt")
    work = Path(args.work) if args.work else out_path.parent / f".{src.stem}.work"
    glossary = load_glossary(args.glossary)

    rc = srt_kit.main(["split", str(src), "--work", str(work),
                       "--batch-size", str(args.batch_size), "--source", args.source])
    if rc != 0:
        return rc

    batch_files = sorted(work.glob("batch_*.json"))
    batches = {f: json.loads(f.read_text(encoding="utf-8")) for f in batch_files}
    failures: list[str] = []
    results: dict[Path, dict[str, str]] = {f: {} for f in batch_files}

    print(f"translating {len(batch_files)} batch(es) with {args.model} "
          f"({args.concurrency} in parallel)")

    done = 0
    with futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        pending = {pool.submit(translate_batch, b, args, glossary): f
                   for f, b in batches.items()}
        for fut in futures.as_completed(pending):
            f = pending[fut]
            try:
                results[f] = fut.result()
            except Exception as exc:  # one bad batch should not lose the rest
                failures.append(f"{f.name}: {exc}")
                print(f"  FAILED {f.name}: {exc}", file=sys.stderr)
                continue
            done += 1
            print(f"  [{done}/{len(batch_files)}] {f.name} -> {len(results[f])} cues")

    for f, translations in results.items():
        if translations:
            f.with_name(f.name.replace(".json", ".vi.json")).write_text(
                json.dumps({"translations": translations}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    if failures and not args.allow_partial:
        print(f"\n{len(failures)} batch(es) failed; nothing written. "
              "Re-run to retry, or pass --allow-partial.", file=sys.stderr)
        return 1

    merge_args = ["merge", str(src), "--work", str(work), "-o", str(out_path)]
    if args.bilingual:
        merge_args.append("--bilingual")
    if args.bom:
        merge_args.append("--bom")
    if failures or args.allow_partial:
        merge_args.append("--allow-missing")
    rc = srt_kit.main(merge_args)
    if rc != 0:
        return rc

    print()
    srt_kit.main(["check", str(out_path), "--against", str(src)])
    if failures:
        print(f"\nNOTE: {len(failures)} batch(es) kept their source text.", file=sys.stderr)
    if not args.work:
        for f in work.glob("*.json"):
            f.unlink()
        work.rmdir()
    return 0


if __name__ == "__main__":
    sys.exit(main())
