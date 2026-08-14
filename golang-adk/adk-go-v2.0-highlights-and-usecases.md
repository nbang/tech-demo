# ADK-Go v2.0.0 — Highlights & Use Cases

> Review of the [google/adk-go v2.0.0 release](https://github.com/google/adk-go/releases/tag/v2.0.0).
> Focus: the new **graph-based workflow engine**, plus practical use cases you can build with it.
>
> Reviewed: 2026-07-03

---

## TL;DR

ADK-Go 2.0 turns the framework from a *hierarchical agent executor* into a **graph-based execution engine**. Your agents, tools, and plain Go functions become **nodes** in a directed graph connected by **edges**, and the runtime handles concurrency, state persistence, human pauses, and resumption across process restarts.

If you've ever tried to build a reliable multi-step agent and fought with "the LLM decided to skip a step," this release is the direct answer: **you get deterministic control over routing and execution, while still using the LLM where judgment is actually needed.**

Three headline features:

1. **Graph-based workflows** — deterministic routing & execution.
2. **Dynamic workflows** — orchestration as ordinary Go code (loops, branching).
3. **Collaborative workflows** — coordinator agents + specialized sub-agents.

---

## Breaking changes (read before upgrading)

| Change | What to do |
|---|---|
| **New module path** | `go get google.golang.org/adk/v2` and rewrite imports from `google.golang.org/adk/...` → `google.golang.org/adk/v2/...` |
| **Go 1.25+ required** | Bump your toolchain. |
| **Unified context** | `ToolContext` + `CallbackContext` are merged into a single `agent.Context`. Node/tool/callback functions now take `agent.Context` instead of `InvocationContext`. |
| **Custom `InvocationContext`** | Must now implement `IsolationScope()` and `ResumedInput(id string)`. |
| **Event struct grew** | New fields: `IsolationScope`, `Output`, `Routes`, `RequestedInput`, `NodeInfo`. `session.NewEvent` now takes a `context.Context`. |
| **Forward-compat testing** | Use the new `agent.StrictContextMock` in tests so interface growth doesn't silently break you. |

A formal v1→v2 migration guide ships with the repo.

---

## The graph engine (the good part)

Applications are described as **a graph of nodes connected by edges**. The execution model handles concurrent runs, state persistence, human pauses, and resumption — even across process restarts.

### Node types

| Node | Purpose |
|---|---|
| **Function node** | Wrap a plain Go function (generic type inference). |
| **Emitting function node** | Same, plus an `emit` callback to stream events or pause for human input. |
| **Agent node** | Embed any `agent.Agent` (e.g. `LlmAgent`) as a graph step. |
| **Tool node** | Turn a `tool.Tool` into a graph step. |
| **Join node** | Fan-in barrier — waits for all predecessors, returns a map of their outputs. |
| **Dynamic node** | Orchestration body is ordinary Go code that calls `RunNode(...)` per child. |
| **Workflow node** | Embed an entire sub-workflow as one node. |
| **Parallel workers** | Run a node concurrently across list items, then aggregate. |
| **State-bound node** | Pull session-state values via `state:"<key>"` struct tags. |

### Edges & routing

A node emits a **routing value**; matching edges fire. Route types: `StringRoute`, `IntRoute`, `BoolRoute`, `MultiRoute`, and `Default`. This gives you sequential chains, conditional routers, fan-out/fan-in, nested sub-graphs, and **first-class loops** (completed nodes can re-trigger).

```go
import "google.golang.org/adk/v2/workflow"

upper  := workflow.NewFunctionNode("upper",  upperFn,  cfg)
suffix := workflow.NewFunctionNode("suffix", suffixFn, cfg)

edges := workflow.Chain(workflow.Start, upper, suffix)

wf, _ := workflowagent.New(workflowagent.Config{
    Name:  "simple_sequence_workflow",
    Edges: edges,
})
```

**LLM-as-router**: let a model classify input and emit a route, while the *graph* stays deterministic:

```
User: "What time is it?"  → agent classifies as "question"    → answering node
User: "Hello world!"      → agent classifies as "exclamation" → reacting node
```

### Dynamic nodes (orchestration = Go code)

```go
greeter := workflow.NewDynamicNode("greeter_workflow",
    func(nc agent.Context, in string, emit func(*session.Event) error) (string, error) {
        return workflow.RunNode[string](nc, greeterNode, in)
    },
    workflow.NodeConfig{},
)
```

Options: `WithRunID`, `WithUseSubBranch`, `WithUseAsOutput`, `WithIsolationScope`.

### Human-in-the-loop (HITL) — durable pause/resume

Any node can pause and ask a human:

```go
event := workflow.NewRequestInputEvent(ctx, session.RequestInput{
    InterruptID:    "approve_refund",
    Message:        "Approve a $200 refund? (yes/no)",
    ResponseSchema: schema,
})
```

- **Resume modes**: *Handoff* (answer flows to next node) or *Re-entry* (paused node re-runs, reads `ctx.ResumedInput(...)`).
- **Durable**: workflow state persists in the session and can be reconstructed by scanning session history — it survives process restarts.
- Responses validate against a schema (`ErrInvalidResumeResponse`, `ErrNothingToResume`).

### Resilience

- **Per-node retries** with exponential backoff + jitter: `workflow.DefaultRetryConfig()` → 5 attempts, 1s initial, 60s cap, 2x backoff, full jitter.
- **Per-node timeouts.**
- **Graph-wide concurrency cap**: `WithMaxConcurrency(n)`.
- **Isolation scopes** keep parallel branches from leaking each other's LLM prompts.

---

## Collaboration: LLM agent modes

`LlmAgent` gains three modes so a coordinator can delegate cleanly with isolation-scoped conversation history:

- **Chat** — interactive back-and-forth with the user.
- **Task** — quietly completes a background task. *(Note: task-mode agents can't be static graph nodes.)*
- **SingleTurn** — one-shot execution.

Mode-specific tools (`finish_task`, `single_turn`, `task`) install automatically.

---

## Unified context & observability

Tools, callbacks, and graph nodes all now receive a single `agent.Context`. Beyond being one fewer type to learn, this produces **one consistent telemetry span tree**, so you can see exactly what your graph did on each run.

---

## Suggested use cases

Ranked roughly by how well they exploit the graph engine.

### 1. Approval / compliance workflows (HITL + durable resume) ⭐
Refunds, expense approvals, content moderation, KYC. An LLM node drafts a decision, a **Join node** collects the evidence, and a **RequestInput** node pauses for a human sign-off. Because resume is durable, the human can approve *hours later* — the workflow reconstructs from session history. This is the killer demo for the release.

### 2. Deterministic RAG / research pipelines ⭐
`retrieve → rerank → synthesize → cite-check → answer` as an explicit chain. Add a **conditional route**: if cite-check fails, loop back to retrieve (first-class loops). You keep the LLM for synthesis but the *pipeline* never skips the citation step. **Directly relevant to your `text2sparql` / `text2sql` work** — you could model `NL → schema-RAG → generate query → validate/execute → repair-on-error` as a graph with a retry loop on the validation node.

### 3. Parallel fan-out enrichment
"Enrich these 500 leads." A **parallel-workers** node runs the enrichment agent across the list with `WithMaxConcurrency(n)`, a **Join node** aggregates, and per-node retries handle flaky upstream APIs. Isolation scopes stop one lead's context bleeding into another.

### 4. Multi-agent coordinator (chat + background tasks)
A **Chat**-mode coordinator talks to the user while it dispatches **Task**-mode specialists (a researcher, a coder, a writer) that report back. Good for "assistant that keeps chatting while work happens in the background."

### 5. Self-correcting code / query generation loop
Generate → run/compile → on error, route back to a "fix" node with the error message; cap attempts via retry config. The loop is *explicit and bounded*, not left to the model's discretion.

### 6. Long-running orchestration that survives restarts
Batch/ETL-style agent jobs (nightly report generation, data reconciliation) where the process may restart mid-run. State persistence + reconstruction from session history means you resume where you left off instead of restarting.

### 7. Tiered routing to control cost/latency
An LLM-as-router node classifies difficulty and emits a route: easy → small/local model node, hard → frontier-model node, ambiguous → HITL. Deterministic edges, model judgment only at the classification step.

---

## A concrete starter for *this* repo

Given your existing NL→query demos, the highest-value experiment is to re-cast one of them as an ADK-Go graph:

```
Start
  └─> classify(intent)                 [LlmAgent node, emits StringRoute]
        ├─ "sparql" ─> schemaRAG ─> genSPARQL ─┐
        └─ "sql"    ─> schemaRAG ─> genSQL    ─┤
                                                ▼
                                          validate/execute   [Function node + RetryConfig]
                                                │  (on error) └──loop back to gen (bounded)
                                                ▼
                                          RequestInput?       [HITL: confirm destructive query]
                                                ▼
                                          format+answer
```

This showcases: LLM-as-router, deterministic chain, a bounded self-repair loop, and optional human approval before executing a query — all the v2.0 headline features in one demo.

---

## Sources

- [ADK-Go v2.0.0 release notes](https://github.com/google/adk-go/releases/tag/v2.0.0)
- [Announcing ADK Go 2.0 — Google Developers Blog](https://developers.googleblog.com/announcing-adk-go-20/)
- [Welcome to ADK 2.0 — adk.dev](https://adk.dev/2.0/)
- [google/adk-go repository](https://github.com/google/adk-go)
