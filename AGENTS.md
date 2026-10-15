# AGENTS.md

Shared instructions for every coding agent working in this repo: Claude Code,
Gemini CLI, Codex, OpenCode / Hermes (DeepSeek, Kimi, …), Cursor, and others.
`CLAUDE.md` and `GEMINI.md` just point here, so edit **this** file.

## What this repo is

`tech-demo` is a **monorepo of independent demos, benchmarks, and guides**. Each
top-level folder is its own project with its own language, deps, venv, and
README. Nothing builds, tests, or lints the whole repo. **Work inside one
project folder at a time.**

| Folder | Kind | Stack | Entry point |
|---|---|---|---|
| `text2sql/` | NL→SQL for Postgres, schema-RAG | Python, FastAPI, Ollama | `.venv/bin/text2sql` |
| `text2sparql-v1/`, `text2sparql-v2/` | NL→SPARQL over RDF, ontology-RAG | Python, rdflib | `.venv/bin/text2sparql` |
| `ocr-bench/` | OCR / doc-parsing benchmark (OmniDocBench) | Python, httpx | `.venv/bin/ocr-bench` |
| `stt-bench/` | Multilingual (en/vi/zh) ASR benchmark | Python, jiwer, MLX | `.venv/bin/stt-bench` |
| `skill-audit/` | Security/quality audit of Agent Skill zips | Python, FastAPI, pytest | `.venv/bin/skill-audit` |
| `purifier-dashboard/` | Live Xiaomi purifier page: LAN poller → Cloudflare Worker + D1 | Python poller, TS Worker, wrangler | `worker/: npm run dev` / `npm run typecheck` |
| `openagent-demo/` | OpenAgent REST API walkthrough | Python, httpx | `.venv/bin/openagent-demo` |
| `golang-adk/nl2query-graph/` | ADK-Go v2 NL→SQL/SPARQL agent | Go | `go run .` / `go test ./...` |
| `langchain4j-agentic-demo/` | LangChain4j agentic patterns | Java, Maven | `mvn …` |
| `qwen-audio-demo/` | Qwen audio / realtime voice agent | Node (ESM) | `npm run demo` |
| `typescript-v7/` | TypeScript 7 (native tsc) showcase | TS, Node | `npm run check` / `npm run dev` |
| `turboquant-guide/` | llama.cpp TurboQuant notes + benchmark | Python script, C++ (vendored) | `benchmark.py` |
| `ecc-demo/` | With/without ECC plugin case study | mixed | `TASK.md` |
| `*-guide/`, `ai-methodology/`, `pi-herdr-orchestrator/` | Written guides and configs | Markdown, shell | — |
| `.claude/skills/srt-translate-vi/` | Skill: translate .srt → Vietnamese | Python | `SKILL.md` |
| `zz-archive/` | Finished/abandoned demos, read-only | mixed | its README |

`gemma-agentic/` is an empty placeholder. Ask before putting anything in it.

## Working rules

### Scope
- Stay inside the project folder you were assigned or that the task names. Don't
  refactor, reformat, or "fix" other projects along the way.
- Don't add repo-wide tooling (root `package.json`, root `pyproject.toml`,
  workspace files, pre-commit, CI) unless asked.
- `text2sparql-v1` and `-v2` are deliberate snapshots of the same package.
  Change only the version the task names. Don't sync the two.
- `zz-archive/` holds finished or abandoned demos. Don't edit, update, or
  run them unless asked. Archiving is `git mv <project> zz-archive/` plus a
  row in `zz-archive/README.md`.
- Don't edit vendored or third-party trees: `turboquant-guide/llama-cpp-turboquant/`,
  `node_modules/`, `target/`, `*.egg-info/`, `.venv/`.

### Environment and commands
- **Python projects:** one venv per project at `<project>/.venv`, installed in
  editable mode. Always call the venv binaries directly; never the system
  `python`/`pip`:
  ```sh
  cd <project> && python3 -m venv .venv && .venv/bin/pip install -e .   # first time only
  .venv/bin/python -m pytest tests/ -q                                    # where tests exist
  ```
- **Node projects:** run `npm install` and `npm run <script>` inside the project folder.
- **Go:** run `go build ./... && go vet ./... && go test ./...` in `golang-adk/nl2query-graph/`.
- **Java:** run `mvn -q compile` / `mvn -q test` in `langchain4j-agentic-demo/`.
- There's no shared formatter config. Match the style of the file you're editing.
- Before saying a change works, run that project's real check: its tests, its
  type-check, or the CLI against the bundled `examples/`. Paste the output. If
  you couldn't run it (no GPU, no remote endpoint, no network), say so.

### Config, secrets, and LLM endpoints
- Config comes from `<project>/.env` (git-ignored); `.env.example` is the
  committed template. **Never print, copy, commit, or paste the contents of a
  `.env` file.** When you add a setting, add it to `.env.example` with a safe
  placeholder and document it in the README.
- Most demos call **OpenAI-compatible endpoints**: a local Ollama
  (`http://localhost:11434`, mostly for embeddings), NVIDIA NIM, or OpenRouter.
  Model IDs go stale fast; NIM retires models without warning. If a call
  returns 404/410 or hangs, suspect the model ID before the code, and check the
  project README for the model currently in use.
- Don't swap a project's chosen model or provider without asking. Several of
  them are deliberate, and the reasons are written in the README or docs.

### Documentation
- Every project has an English `README.md`. Most also have a Vietnamese guide
  at `docs/huong-dan-<project>.md`. If you change behavior, CLI flags, or
  config, **update both** and keep the Vietnamese guide in Vietnamese.
- Benchmark results under `results/` are generated. Don't hand-edit them;
  re-run the benchmark instead.

### Home-LAN device runbooks live elsewhere
- `home-network/` moved out of this repo to its own project at
  `~/work/home-network/` (device runbooks, IPs, inventory). Don't recreate it
  here; edit device docs in that project.
- The `purifier-dashboard/` poller talks to a real device on the LAN. Don't run
  it against the purifier or touch the deployed Worker unless the user asks in
  the current task.

## Multi-agent coordination

Several agents may work in this repo at the same time. To keep them from
colliding:

1. **One agent per project folder.** Claim a folder by stating it at the start
   of your task. If you have to touch a second folder, stop and ask.
2. **Prefer a git worktree or branch per agent** for anything bigger than a doc
   edit:
   `git worktree add ../tech-demo-<agent>-<task> -b <agent>/<task>`.
3. **The working tree is usually dirty** with unrelated edits from the user or
   other agents. Never run `git add -A`, `git add .`, `git commit -a`,
   `git stash`, `git checkout -- .`, `git reset --hard`, or `git clean`. Stage
   only the paths you changed, by name.
4. **Commit only when asked.** Messages use conventional prefixes, as in the
   history: `feat: add <project> — <one-line summary>`, `fix(<project>): …`,
   `docs(<project>): …`. Never push or force-push without being asked.
5. **Hand off in writing.** When you stop, leave a short note in your final
   message covering what changed (paths), what you verified and how, and what's
   left. Long-running plans go in `<project>/docs/`, not in this file.
6. **Reviewing another agent's work:** read the diff (`git diff -- <project>/`)
   and run the project's checks yourself. Don't trust the other agent's
   summary.

### Suggested split by agent strengths
These are only suggestions; the user decides.
- **Planner / reviewer:** reads the code, writes the plan in `docs/`, and
  reviews diffs. Usually doesn't write code itself.
- **Implementer(s):** one per project folder or worktree, following the plan.
- **Cheap/fast models** (DeepSeek, free OpenRouter models via Hermes/OpenCode):
  doc updates, Vietnamese translations of guides, `.env.example`/README sync,
  running benchmarks and summarizing results.
- **Any task that touches real LAN hardware, secrets, or git history** needs a
  human in the loop.

## New project checklist
1. A new top-level folder `<name>/` (kebab-case), self-contained.
2. `README.md` (English) with what it is, quickstart, config table, and
   example run.
3. `docs/huong-dan-<name>.md` (Vietnamese walkthrough) if it's a demo.
4. `.env.example` if it reads any config. The project's own `.gitignore` covers
   `.venv/`, `node_modules/`, build output, and caches.
5. A runnable example in `examples/` so the next agent can verify changes.
