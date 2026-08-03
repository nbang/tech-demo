---
name: srt-translate-vi
description: Translate .srt subtitle files from English or Chinese into Vietnamese, preserving every original timecode. Use when the user asks to translate, dịch, or localise subtitles, an .srt/subtitle file, or captions into Vietnamese (tiếng Việt) — or to produce a bilingual subtitle track. Covers single files and whole folders.
---

# Translate .srt subtitles to Vietnamese

Timecodes are never re-typed by a model. `scripts/srt_kit.py` parses the source
file, hands out **text only**, then rebuilds the output by copying each index and
timing line verbatim from the original. Desynchronised subtitles are structurally
impossible; the only thing that can go wrong is the wording.

Two paths. Pick by size and whether quality or unattended throughput matters more.

## Path A — translate in-context (default)

Best quality: full conversation context, consistent pronouns and register. Use
for anything up to a few thousand cues.

### 1. Inspect
```bash
python3 .claude/skills/srt-translate-vi/scripts/srt_kit.py stats INPUT.srt
```
Confirms cue count, detected encoding (Chinese files are often GB18030) and the
source language. If the language guess is wrong, pass `--source en|zh` in step 2.

### 2. Split into batches
```bash
python3 .claude/skills/srt-translate-vi/scripts/srt_kit.py split INPUT.srt \
  --work /tmp/srtwork --batch-size 40
```
Writes `/tmp/srtwork/batch_001.json …`. Each cue carries `id`, `text`, `duration`
and `max_chars` — a length budget at ~17 chars/second.

### 3. Translate each batch, in order
Read `batch_NNN.json`, then write `batch_NNN.vi.json` next to it:
```json
{ "translations": { "1": "Chào buổi sáng.", "2": "Cậu đến muộn\nmười phút rồi." } }
```
Rules — these matter more than literal accuracy:
- **One key per input `id`.** Never merge, split, drop or reorder cues. If a
  sentence spans cues 12–14, translate it as a whole and distribute the
  Vietnamese across the same three keys.
- Stay within `max_chars`; use at most 2 lines, separated by a single `\n`.
- Copy markup verbatim: `<i>`, `<b>`, `<font …>`, `{\an8}`.
- Keep the pronoun system consistent across the whole file — decide
  tôi/anh/em/cậu/ông per speaker pair early and carry it through. Read the
  previous batch's `.vi.json` before starting the next one.
- Music-only cues (`♪`) stay as-is; translate bracketed sound cues
  (`[door slams]` → `[tiếng cửa đập]`).
- No translator notes, no romanisation, no commentary.

See [references/style-vi.md](references/style-vi.md) before the first batch —
it covers register, Chinese name handling, line-breaking and the common traps.
Write batch files with the Write tool (never `echo`) so escaping stays correct.

### 4. Merge and verify
```bash
python3 .claude/skills/srt-translate-vi/scripts/srt_kit.py merge INPUT.srt \
  --work /tmp/srtwork -o OUTPUT.vi.srt
python3 .claude/skills/srt-translate-vi/scripts/srt_kit.py check OUTPUT.vi.srt --against INPUT.srt
```
`merge` **aborts** if any cue lacks a translation and names the missing ids — go
back and write them rather than reaching for `--allow-missing`. `check` proves
timings, indices and markup are unchanged, and flags over-long or too-fast lines.
Fix anything it reports, then re-merge.

## Path B — unattended batch CLI

For long files or whole folders. Same split/merge core, so the timing guarantee
is identical. Each batch goes out as one request carrying the full translator
rule set in the system prompt, and comes back as JSON keyed by cue id.

Defaults to NVIDIA's hosted **`deepseek-ai/deepseek-v4-flash`**.

```bash
export SRT_API_KEY=nvapi-...     # from build.nvidia.com; or put it in .env

python3 .claude/skills/srt-translate-vi/scripts/translate_srt.py INPUT.srt -o OUTPUT.vi.srt
```
The key is read from `SRT_API_KEY`, falling back to this skill's `.env` (see
`.env.example`; the file is gitignored). Real environment variables win over it.

Useful flags: `--concurrency 4`, `--batch-size 25`, `--source zh`,
`--glossary terms.tsv`, `--bilingual`, `--work DIR` (keep batch files for
inspection), `--allow-partial` (keep source text for failed batches instead of
aborting). It runs `check --against` automatically at the end.

Point at any other OpenAI-compatible endpoint — a local server, another host —
by overriding the two env vars:
```bash
export SRT_API_BASE=http://localhost:11434/v1
export SRT_MODEL=your-model
```

Confirm the endpoint before a large job:
```bash
curl -s "$SRT_API_BASE/models" -H "Authorization: Bearer $SRT_API_KEY" | head -20
```

**Pick a capable model.** Measured on `examples/sample_en.srt`, small models
degrade badly at this task: `meta/llama-3.1-8b-instruct` rendered "umbrella" as
"cái ôm" (hug), invented a Vietnamese name for "Riverside", and blew the 42-char
budget on two cues despite being given `max_chars`. Transient `529 Overloaded`
from NVIDIA is normal and the retry/backoff absorbs it.

For a folder, loop and report per-file results:
```bash
for f in subs/*.srt; do
  python3 .claude/skills/srt-translate-vi/scripts/translate_srt.py "$f" \
    -o "${f%.srt}.vi.srt" || echo "FAILED: $f"
done
```

## Options worth surfacing to the user
- `--bilingual` (on `merge` or `translate_srt.py`) keeps the original text under
  the Vietnamese — good for language learners.
- `--bom` writes UTF-8 with BOM; a few older hardware players need it.
- A glossary TSV (`source<TAB>vietnamese`) pins character names and recurring
  terms. Offer to build one from a first pass over the file for series work.

## Non-negotiables
- Never hand-edit timing lines, and never write an output `.srt` by hand — always
  go through `merge`, then `check --against` the original.
- Output is UTF-8 (`utf-8-sig` with `--bom`); never write the source encoding back.
- Default output name is `<input>.vi.srt` alongside the source. Never overwrite
  the input file.
- Report `check` warnings to the user instead of silently accepting them.
