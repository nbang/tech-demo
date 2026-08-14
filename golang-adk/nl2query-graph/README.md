# nl2query-graph — ADK-Go v2.0 workflow demo

A runnable demonstration of the [ADK-Go v2.0 graph-based workflow engine](../adk-go-v2.0-highlights-and-usecases.md), applied to a **natural-language → query** pipeline (the "text2sparql / text2sql as a graph" use case) that **actually executes** the generated queries against real data.

This is a **hybrid, fan-out/parallel** pipeline modelled on adk-go's [`examples/workflow/complex`](https://github.com/google/adk-go/tree/main/examples/workflow/complex): rather than routing a question to one backend, it asks **both** backends **concurrently** and synthesises a single answer.

## What it shows

| Feature | Where |
|---|---|
| **Fan-out / parallel** | `EdgeBuilder.AddFanOut` runs generation (then execution) across both backends concurrently |
| **Fan-in / join** | two `workflow.NewJoinNode`s act as barriers — one gathers both generated queries, one gathers both results — each as a `map[string]any` keyed by node name |
| **Real query generation** | each branch's LLM call turns question + schema into a query (text2sql / text2sparql) |
| **Human-in-the-loop review** | after generation, one `ResumeOrRequestInput` re-entry node shows **both** queries and lets you **approve or edit** them before anything executes |
| **Per-node retries** | the generation nodes carry `workflow.DefaultRetryConfig()` (5 attempts, backoff + jitter) |
| **Execution** | approved SQL runs against **SQLite**; approved SPARQL runs against a **Turtle file** |
| **Synthesis** | a final `LlmAgent` node reconciles the relational and graph results into one grounded answer |

## Graph

```
START ─┬─▶ gen_sql(LLM)    ─┐
       └─▶ gen_sparql(LLM)  ─┤                 (generation runs in parallel)
                            ▼
                   gather_gen (JoinNode: both queries)
                            ▼
                   review (HITL: approve, or revise either query)
                            ▼
       ┌────────────────────┴────────────────────┐
       ▼                                          ▼
   exec_sql(SQLite)                        exec_sparql(TTL)   (execute in parallel)
       └────────────────────┬────────────────────┘
                            ▼
                   gather_res (JoinNode: both results)
                            ▼
                   format ─▶ synthesize(LLM)
```

The LLM drafts a SQL and a SPARQL query in parallel; `gather_gen` joins them; the **review** node pauses so a human can approve both or edit either; the approved queries execute in parallel against their stores; `gather_res` joins the results; and the synthesis agent produces one answer, flagging any discrepancy. Execution errors are folded into each branch's output so one backend failing never deadlocks the join.

> The graph is built in `buildHybrid()`, which `TestBuildHybridGraph` exercises through `workflowagent.New` (edge validation) — so the wiring is checked without a live endpoint.

## Configure

Copy [.env.example](.env.example) → `.env` and edit it (loaded via `godotenv`; real env vars still win):

```bash
OPENAI_API_KEY=nvapi-...                        # your NVIDIA key (or OPENAI_API_KEY)
OPENAI_BASE_URL=https://integrate.api.nvidia.com/v1
OPENAI_MODEL=nvidia/gemma4:31b
SQLITE_PATH=./examples/shop.db                  # auto-created + seeded if missing
TTL_PATH=./examples/kg.ttl                      # sample knowledge graph ships here
```

## Run

```bash
cp .env.example .env   # then edit .env
go mod tidy
go run . console
```

Example session — both queries drafted in parallel, reviewed by you, then executed:

```
User  -> Which products are in the accessories category?
Agent -> Review the generated queries before execution.
         Reply "yes" to run both as-is, or override one/both with lines like:
           sql: SELECT ...
           sparql: PREFIX ex: <http://example.org/> SELECT ...

         [SQL]
         SELECT name FROM products WHERE category = 'accessories'

         [SPARQL]
         PREFIX ex: <http://example.org/>
         SELECT ?name WHERE { ?p a ex:Product ; ex:category "accessories" ; ex:name ?name . }

User  -> yes
Agent -> Both backends agree: the accessories products are USB-C Hub and Laptop
         Stand (2 items).
```

To revise, reply with a replacement instead of `yes`, e.g.:

```
User  -> sql: SELECT name, price FROM products WHERE category = 'accessories' ORDER BY price
```

Only the SQL query is overridden; the SPARQL query keeps its generated value. Empty
reply or `yes`/`y` accepts both as drafted.

Product `name`/`price`/`category` values are mirrored between the two stores, so
questions like *"which products cost more than 100"* or *"products in the audio
category"* let you watch the relational and graph backends corroborate each other.

## Sample data (ships in `examples/`)

- **SQLite** — auto-seeded on first run: `products(id, name, price, category)` (6 rows) and `customers(id, name, city)` (3 rows).
- **Turtle** — [examples/kg.ttl](examples/kg.ttl): 6 `ex:Product` nodes with `ex:name`/`ex:price`/`ex:category` (mirroring the `products` table), and 3 `ex:Person` nodes linked by `ex:knows`.

The product `name`/`price`/`category` values match between the two stores, so a question like *"which products are in the accessories category"* is answered identically by both backends — letting the synthesis step confirm they agree. `ex:knows` is a graph-only relationship, so *"who does Alice know"* is answered by the SPARQL branch alone (the SQL branch reports it has no such data). Other good questions: *"list products under 100"*, *"what is Bob's name"*.

## Files

| File | Role |
|---|---|
| [main.go](main.go) | builds and runs the graph |
| [config.go](config.go) | `.env` / env loading |
| [openai_model.go](openai_model.go) | `model.LLM` adapter over the official OpenAI Go client |
| [exec_sql.go](exec_sql.go) | SQLite executor + sample-data seeding |
| [exec_sparql.go](exec_sparql.go) | Turtle loader + SPARQL-subset executor |
| [exec_test.go](exec_test.go) | validates both executors against the sample data (`go test`) |

## Notes & limitations

- **Requires Go 1.25+** (ADK v2 requirement); module path `google.golang.org/adk/v2`.
- **`genai` is not removable.** ADK's `model.LLMResponse.Content` is a `*genai.Content` — genai is part of ADK's public model interface, so any `model.LLM` implementation must import it. It's used minimally, only in `openai_model.go`.
- **The SPARQL engine is a documented subset, not full SPARQL 1.1.** Go has no mature embedded SPARQL engine, so `exec_sparql.go` implements just what the generator is prompted to emit: PREFIX, `SELECT`, basic triple patterns (`s p o .`), and `FILTER(?var OP number)`. Turtle *parsing* is full-featured (via `github.com/knakk/rdf`); only the query engine is limited. Out-of-subset queries (OPTIONAL, UNION, aggregates, property paths) return an error rather than a wrong answer. The `gen_sparql` prompt constrains the model to the supported shape.
- **SQL runs as-is against SQLite** (pure-Go `modernc.org/sqlite`, no cgo), so the full SELECT surface works.
- Verified: `go build`, `go vet`, and `go test` all pass. The executor tests run without an API key; the end-to-end LLM flow needs a real key.
