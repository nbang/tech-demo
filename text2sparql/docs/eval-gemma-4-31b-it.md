# Evaluation report — `google/gemma-4-31b-it`

**Task:** natural-language → SPARQL over the two demo knowledge graphs
(`shop_demo.ttl`, schema.org; `acme_kg.ttl`, W3C Org + GeoNames + SKOS).
**Provider:** NVIDIA NIM (`https://integrate.api.nvidia.com/v1`, OpenAI-compatible, streaming, `temperature=0`).
**Harness:** `text2sparql eval examples/eval.jsonl` — 8 gold cases, set-based matching (order/column-insensitive).
**Date:** 2026-06-30.

## Headline

| Model | Score | Notes |
|---|---:|---|
| **MiniMax M3** (remote, NVIDIA) | **8 / 8 (100%)** | current reference |
| **gemma-4-31b-it** (remote, NVIDIA) | **6 / 8 (75%)** suite · **7 / 8 effective** | 1 transient, 1 systematic miss |
| **qwen3.5:4b** (local, Ollama) | **2 / 8 (25%)** | too small for SPARQL/property paths |

> gemma's suite score was 6/8, but one of the two failures (HQ-country) is a **transient** that passed 5/5 on isolated re-run. Its only *repeatable* miss is a column-projection mismatch on the aggregation question. Effective competence is ~7/8.

## gemma per-case results

| # | Graph | Question | Result |
|---|---|---|:--:|
| 1 | shop | Which customer placed the most orders? | ❌ (projection) |
| 2 | shop | List the names of all customers in Vietnam (country VN) | ✅ |
| 3 | shop | What is the name of the most expensive product? | ✅ |
| 4 | acme | List the names of everyone who is an employee, including managers | ✅ |
| 5 | acme | List the names of everyone that Tom Becker reports to, directly or indirectly | ✅ |
| 6 | acme | Which country is the ACME Corp HQ located in? | ❌ suite / ✅ 5×5 re-run (transient) |
| 7 | acme | List the names of every sub-organization under ACME Corp at any depth | ✅ |
| 8 | acme | List the names of people who have any kind of machine learning skill | ✅ |

The hard graph-native cases all pass: transitive management chain (`org:reportsTo+`, #5),
org-hierarchy property path (#7), and the SKOS skill taxonomy with materialized types (#8).
gemma handles property paths and the schema-grounding correctly.

## The two failures

### #1 — "Which customer placed the most orders?" (systematic)

gemma's query (stable across runs):

```sparql
PREFIX ex: <http://example.org/shop#>
PREFIX schema: <https://schema.org/>
SELECT ?customerName
WHERE {
  ?order a schema:Order ;
         schema:customer ?customer .
  ?customer schema:name ?customerName .
}
GROUP BY ?customerName
ORDER BY DESC(COUNT(?order))
LIMIT 1
```
→ rows: `[['Alice Nguyen']]`

**Verdict: borderline / scoring artifact.** The logic is *correct* — it groups by customer,
orders by descending order-count, and returns the top one (**Alice Nguyen, the right answer**).
The only mismatch is that it projects just the name, while the gold row is `['4', 'Alice Nguyen']`
(count **and** name). The question literally asks "*which* customer", so gemma's answer is arguably
right; the set-based checker fails it only because the expected set includes the count `4`.

*Fix options:* (a) loosen the gold to `['Alice Nguyen']` / subset-match, or (b) keep it strict to
reward models that surface the supporting count — MiniMax M3 does add the count column, which is the
discriminating behavior the case was designed to test. Recommend keeping it strict and recording
gemma's miss as "answer correct, count column omitted."

### #6 — "Which country is the ACME Corp HQ located in?" (transient)

gemma's query (identical on all 5 isolated re-runs, all returning `['United States']`):

```sparql
PREFIX ex: <http://example.org/data#>
PREFIX gn: <http://www.geonames.org/ontology#>
PREFIX schema: <https://schema.org/>
SELECT ?countryName WHERE {
  ?company a org:Company ;
           schema:name "ACME Corp" ;
           org:basedIn ?hq .
  ?hq gn:locatedIn+ ?country .
  ?country a gn:Country ;
           schema:name ?countryName .
}
```
→ rows: `[['United States']]` ✅

**Verdict: not a real weakness.** This query correctly walks `org:basedIn` then the transitive
`gn:locatedIn+` (building → city → country). It passed **5/5** on a dedicated stability run; the lone
suite failure (empty result) was a one-off — almost certainly a transient empty API envelope on that
single call, the same NVIDIA-NIM flakiness already seen with MiniMax. (Note: the undeclared `org:`
prefix resolves fine because rdflib seeds query namespaces from the loaded graph's bound prefixes.)

## Stability check (HQ-country, gemma, 5×)

```
run 1: PASS  ['United States']
run 2: PASS  ['United States']
run 3: PASS  ['United States']
run 4: PASS  ['United States']
run 5: PASS  ['United States']
```

## Conclusion

`gemma-4-31b-it` is a **viable generator for this task** — effectively 7/8, matching MiniMax M3 on
every conceptually hard case (class hierarchy, transitive paths, taxonomy, schema-grounding) and
losing only on a count-column projection nuance. It is meaningfully stronger than the 4B local model
(2/8), which fails on basic name-resolution, aggregation, filtering, and even SPARQL syntax.

**Recommendation:** MiniMax M3 stays the reference (8/8, including the aggregation-with-count case).
gemma-4-31b-it is a solid second choice when a Google-family / smaller model is preferred — the only
behavioral gap is that it under-projects on "top-N + supporting metric" questions.
