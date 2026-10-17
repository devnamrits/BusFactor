<div align="center">

# BusFactor

**Know who your team can't lose — and fix it before they leave.**

*Everyone measures the bus factor. BusFactor simulates it — and heals it.*

![FalkorDB](https://img.shields.io/badge/graph-FalkorDB-e6174b?style=flat-square)
![Python + FastAPI](https://img.shields.io/badge/agent-Python%20%2B%20FastAPI-3572A5?style=flat-square)
![React](https://img.shields.io/badge/console-React%20%2B%20force--graph-61DAFB?style=flat-square)

</div>

> **What this is.** A knowledge-graph agent that maps who knows what across a repository, **simulates losing a person** on a clone of the graph, produces a **handover plan**, and **proves the fix by re-running the same simulation with the plan applied** — then acts on it (real GitHub issue / runbook PR) and exposes the same tool catalogue over **MCP** so any coding agent can consult it.
>
> **The name.** *Bus factor* = how many people the project can lose before it's in trouble. For most teams it's 1. BusFactor makes that number something you can **rehearse — and raise**.
>
> This single document is the product and system specification.

## Contents

1. [The problem](#1-the-problem)
2. [Philosophy: six principles](#2-philosophy-six-principles)
3. [Features: what you see, what the graph computes, why](#3-features-what-you-see-what-the-graph-computes-why)
4. [Glossary: speak the language](#4-glossary-speak-the-language)
5. [Architecture and invariants](#5-architecture-and-invariants)
6. [Graph data model](#6-graph-data-model)
7. [Simulation engine](#7-simulation-engine)
8. [The agent, the trust layer, memory](#8-the-agent-the-trust-layer-memory)
9. [FalkorDB utilization map](#9-falkordb-utilization-map)
10. [API, console, actions, MCP, deployment](#10-api-console-actions-mcp-deployment)
11. [Non-goals](#11-non-goals)

---

## 1. The problem

A team's fragility doesn't live in its people — it lives in the **edges** between them and everything else: the engineer who is the only bridge between two subsystems, the decision that exists in exactly one head because no ADR was ever written, the module three people *touch* but only one *understands*. None of these can be read off a person, a file, or a score. They are properties of the network around a person.

| Today's attempt | What it gives you | What it can't |
|---|---|---|
| Org chart | Who reports to whom | Reporting lines aren't dependence lines. Says nothing about knowledge. |
| Git dashboards (busfactor.tech, Mapnostics, truck-factor research) | A static concentration metric ("your bus factor is 1") | Activity ≠ dependence. Blind to reviews, decisions, docs. No consequences, no what-if, no fix. |
| Chat-with-the-repo (text RAG) | Fluent summaries of docs | No mechanism for consequence: asked "what if X leaves", it answers with a confident guess. No proof for any claim. |
| A human audit | A snapshot opinion, once | Stale the day it's written; humans can't introspect graph structure anyway. |

Aviation has simulators. Surgery has drills. Infrastructure has game days. Knowledge loss is the one crew-ending event nobody rehearses — not because teams don't care, but because until now there was no way to run the drill. **You can't game-day a resignation. You can simulate one.**

## 2. Philosophy: six principles

**P1 · Risk lives on edges, not nodes.** Bus factor is not a property of a person; it's a property of the graph around them. You can't read it off a box — you have to look at the wires.

**P2 · You can't audit what you can't remove.** Metrics give numbers and guilt. Consequences require experiment: remove the person and watch — on a copy of the world, where nothing real is harmed.

**P3 · A rehearsal beats a report.** Every high-stakes discipline rehearses its failure modes because rehearsal is cheaper than failure. BusFactor is that missing drill, for knowledge.

**P4 · Diagnosis without a plan is a horoscope.** The simulation ends in an ordered handover plan — and then **re-runs the disaster with the plan in place**. We don't trust the plan. We test it.

**P5 · An answer you can't audit is an oracle.** Every claim cites the exact hops that prove it; every number is validated against rows the database actually returned; refusals are first-class.

**P6 · The graph is the physics.** Copy worlds, remove nodes, recompute connectivity and centrality, diff worlds — this is graph computation, not an app over a database. Remove FalkorDB and BusFactor doesn't get slower; it stops being possible. Every feature must clear this bar.

## 3. Features: what you see, what the graph computes, why

| Feature | What the user sees | What the graph computes | Why it's like that |
|---|---|---|---|
| **Knowledge map** | Interactive graph of people ↔ modules ↔ docs ↔ decisions | Derived `KNOWS` edges, recency-weighted from commits, reviews, issue references, CODEOWNERS | Risk lives on edges (P1) — you must see the wires, not boxes |
| **Load-bearing people** | Ranked list + evidence paths per name | Betweenness on G_k (bridges) + module PageRank rollup + sole-knower tallies | A ranked *prior* — the drill is the ground truth (P2) |
| **What-if simulation** | Pick a person → "Run simulation" | `GRAPH.COPY` → `sim:<id>`; remove their `KNOWS`/`OWNS` edges; recompute components/centrality; diff vs main | You can't audit what you can't remove (P2) |
| **Knowledge islands** | "4 islands — 23 modules left with zero knowers" | WCC on G_k before vs after (isolates are size-1 components) | The shatter, made measurable and clickable |
| **Decisions at risk** | "These 2 decisions lose their only owner" | Pattern match over `DECIDED_BY` + absence of a `RECORDS` doc | Rationale loss is silent and unrecoverable — worth its own signal |
| **Handover plan** | Successor pairs + rationale ("they already review your PRs", "they wrote the RFC") | `algo.SPpaths` over weighted `KNOWS` (cost = 1 − weight) + review-channel overlap + doc authorship | Diagnosis must end in a plan (P4) |
| **Heal loop** | "Re-simulate after plan" → shatter reverses, counters move | Projected `KNOWS {source:'plan'}` edges in a fresh clone; algorithms re-run; metrics recomputed and diffed | Proof, not promise: re-run the disaster with the fix in place (P4) |
| **Memory** | Past simulations with dates and trend ("weakest node moved from X to Y"); recalled at session start | `Sim`/`Finding`/`Question` nodes written back; `CITED`/`TRIGGERED` edges; traversal-based recall | Institutional memory of risk; memory = more nodes, not vectors |
| **Actions** | "Open handover issue" → a real GitHub issue + runbook PR draft appears | Plan steps + evidence paths → GitHub payload (scoped token, preview by default) | Closes the loop from diagnosis to action — agents that *act* |
| **MCP server** | Use BusFactor from Claude Code / Cursor | The same 8-tool catalogue exposed over MCP — one implementation, two surfaces | Meet developers where they work; FalkorDB-native pattern |

**The loop:** Ingest → Ask → Drill (shatter) → Proof (click) → Plan → Act (issue/PR) → Heal (re-simulate, verify) → Remember (next session starts smarter).

## 4. Glossary: speak the language

| Term | Meaning |
|---|---|
| **Bus factor** | The number of people a project can lose before it's in trouble. Per module: count of active people who can work on/explain it. Team bus factor: the minimum across modules. |
| **KNOWS edge** | Person → Module relationship, weight 0–1, tagged `source: traced / inferred / plan`. The core derived fact of the system. |
| **G_k (knowledge view)** | Subgraph `{Person, Module, Doc}` + `{KNOWS, OWNS, DOCUMENTS}` — the view all connectivity analysis runs on. |
| **Knowledge island** | A WCC component of G_k with ≥1 module and **0 active people**: nobody remaining can explain it. |
| **Sole knower / load-bearing person** | The only active person connected to a module (its bus factor is 1) / a person whose removal shatters large regions of the graph. |
| **Bridge** | A person whose removal splits G_k into ≥2 components that each contain people. |
| **Orphaned decision** | A `Decision` with no active decider **and** no doc recording its reasoning. |
| **Review blindspot** | A module with recent PR activity whose reviewers have all departed. |
| **Drill** | One what-if simulation: clone world → remove person → recompute → diff. Visual: the shatter. |
| **Heal** | Apply the plan as projected edges in a fresh world, re-run the same drill, measure the delta. |
| **World** | One FalkorDB graph: `main` (observed reality) or `sim:<id>` (a what-if). Kept for replay. |
| **Projected edge** | A hypothetical knowledge edge from the plan, `source:'plan'`, existing **only inside sim worlds**, rendered gold. |
| **Finding** | A claim produced by a drill (island, sole-knower, orphaned decision…) with severity + proof paths. |
| **Outcome shape** | Label on every answer: `answered_with_path` / `answered_from_memory` / `not_in_graph` / `unknown_person`. |
| **Show your work** | The audit panel: which tool ran, on which world, with which query, in how long, returning what. |

## 5. Architecture and invariants

```mermaid
flowchart LR
  subgraph Client
    UI["Console UI<br/>React + Vite + force-graph"]
  end
  subgraph Server["Agent API — FastAPI"]
    ROUTER["Turn loop<br/>resolve to plan to execute to validate"]
    LLM{{"LLM<br/>plans tool calls, narrates,<br/>never writes Cypher"}}
    TOOLS["Tool catalogue<br/>8 fixed tools"]
    SIM["Sim engine<br/>copy, surgery, recompute, diff"]
    VAL["Validator + memory writer"]
  end
  subgraph Data["FalkorDB instance"]
    MAIN[("main — the real world")]
    WORLDS[("sim:* — what-if worlds")]
  end
  UI -->|"REST + SSE steps"| ROUTER
  ROUTER --> LLM
  LLM --> ROUTER
  ROUTER --> TOOLS
  ROUTER --> SIM
  TOOLS -->|"RO_QUERY reads"| MAIN
  SIM -->|"GRAPH.COPY + writes"| WORLDS
  SIM -->|"RO reads"| MAIN
  SIM -.->|"findings + metrics"| ROUTER
  ROUTER --> VAL
  VAL -->|"audit nodes"| MAIN
```

| Component | Tech | Responsibility |
|---|---|---|
| Console UI | React 18 + Vite + TS + `react-force-graph-2d` + zustand | Render worlds; run flows; evidence panel. Canvas for 60fps at thousands of edges. |
| Agent API | Python 3.12 + FastAPI + official `falkordb` client | Turn loop, tool execution, validation, memory. Python client is first-class for `algo.*`, `GRAPH.COPY`, `RO_QUERY`. |
| Tool catalogue | 8 tools; queries as versioned `.cypher` files | The only graph access the agent has. |
| Sim engine | `GRAPH.COPY` + Cypher surgery + algorithm recompute + diff | Drill/heal worlds. |
| FalkorDB | Docker image / FalkorDB Cloud | `main` + `sim:*` worlds — the substrate. |
| LLM | OpenAI-compatible endpoint (env-configured) | Tool planning + narration only. No Cypher, no ingestion. |

**Invariants — the constitution. If a feature can't satisfy these, the feature changes:**

| # | Rule | Why |
|---|---|---|
| I1 | FalkorDB is the substrate, not the storage. Every capability lands as graph computation. | The "remove the graph and it stops being possible" bar. |
| I2 | The LLM never writes Cypher. Only the frozen 8-tool catalogue; queries are versioned files. | Determinism, audit, injection safety, explainability. |
| I3 | Worlds are isolated. `main` is never mutated by agent flows; drills/heals live in `sim:<id>`; projected edges only there, tagged `source:'plan'`. | What-if must never contaminate the record. |
| I4 | Every answer cites evidence returned this turn; refusals are first-class. | An answer you can't audit is an oracle. |
| I5 | Everything deterministic: sha256-pinned snapshot, fixed algorithm seeds (`samplingSeed 42`), pinned demo scenario. | Reproducible benchmark; reliable results. |
| I6 | Reads are read-only (`ro_query`), everywhere except inside sim worlds. | Blast-radius containment. |
| I7 | Main-graph writes are additive and auditable only: ingest output + audit nodes (Question/Sim/Finding/Plan/Step). No destructive ops outside sims. | History is append-only. |
| I8 | External actions (GitHub writes) are preview-first, token-scoped, and never target third-party repos. | Acting on reality must never risk anyone else's data. |
| I9 | One implementation per capability: MCP tools wrap the *same* functions as the HTTP API. | One code path, one truth. |

## 6. Graph data model

```mermaid
erDiagram
    PERSON {
        string id PK
        string name
        string handle
        string status "active or departed"
    }
    MODULE {
        string id PK
        string name
        string path
        float  criticality "cached PageRank"
    }
    SIM {
        string id PK
        string kind "drill or heal"
        string label
        string status
    }
    FINDING {
        string id PK
        string kind
        string severity
        string claim
    }
    STEP {
        string id PK
        string kind "pair or doc or review or own"
        int    order
    }
    PERSON ||--o{ MODULE : KNOWS
    PERSON ||--o{ MODULE : OWNS
    PERSON ||--o{ PR : AUTHORED
    PERSON ||--o{ PR : REVIEWED
    PR ||--o{ MODULE : TOUCHES
    PERSON ||--o{ DOC : WROTE
    DOC ||--o{ MODULE : DOCUMENTS
    DOC ||--o{ DECISION : RECORDS
    DECISION ||--o{ PERSON : DECIDED_BY
    DECISION ||--o{ MODULE : AFFECTS
    PERSON ||--o{ PERSON : INTERACTS
    SIM ||--|| PERSON : TARGETS
    SIM ||--o{ FINDING : FOUND
    FINDING ||--o{ MODULE : ABOUT
    PLAN ||--o{ STEP : HAS_STEP
    PLAN ||--|| SIM : BASED_ON
    STEP ||--o{ PERSON : SUBJECT
    STEP ||--o{ PERSON : TEACHER
    STEP ||--o{ MODULE : COVERS
    QUESTION ||--o{ MODULE : CITED
    QUESTION ||--o{ SIM : TRIGGERED
```

**Node properties (only what's used):** `Person {id, name, handle, role?, status, first_seen, last_seen}` · `Module {id, name, path, commits_window, criticality}` · `Doc {id, path, title, kind}` · `Decision {id, title, status, decided_at, source_path}` · `PR {number, title, merged_at, files_changed}` · `Sim {id, kind, label, target_person, status, created_at, metrics_json}` · `Finding {id, kind, severity, claim, proof_json, created_at}` · `Plan {id, label, target_person, status, created_at}` · `Step {id, kind, order, note}` · `Question {id, text, outcome, created_at}`.

**Edge properties:** `KNOWS {weight 0..1, source: traced/inferred/plan, cost = 1 − weight, last_at}` · `OWNS {since, source}` · `AUTHORED {commits}` · `REVIEWED {reviews, last_at}` · `TOUCHES {files, additions}` · `INTERACTS {n, last_at}` · audit edges `TARGETS, FOUND, ABOUT, HAS_STEP, BASED_ON, SUBJECT, TEACHER, COVERS, CITED, TRIGGERED`.

**G_k for islands** = nodes `{Person, Module, Doc}`, edges `{KNOWS, OWNS, DOCUMENTS}`. Decisions are analyzed by their own query (owner + records), because "who can explain this" and "does this decision still have an owner" are different questions. `INTERACTS` is excluded from G_k — it merges people, not explainability.

```cypher
// indexes (created by the loader)
CREATE INDEX FOR (p:Person) ON (p.name)
CREATE INDEX FOR (m:Module) ON (m.id)
CREATE INDEX FOR (m:Module) ON (m.name)
CREATE INDEX FOR (d:Doc) ON (d.path)
```

## 7. Simulation engine

**Pinned definitions:**

```
R(m)              = |{ p : Person, p.status='active', (p)-[:KNOWS|OWNS]->(m) }|  // module coverage
module bus factor = R(m)
team bus factor   = min over modules with R(m) > 0 in main (pre-existing zeros tracked separately)
island(sim)       = WCC component of G_k with >=1 Module and 0 active Persons
sole_knower_lost  = R(m) was 1 in main, now 0
orphaned_decision = Decision with 0 active DECIDED_BY and 0 Doc RECORDS
review_blindspot  = Module active in window whose reviewers all departed
bridge_lost       = departure splits G_k into >=2 components that each contain an active Person
coverage_thin     = R(m) dropped below K (K=2) but stayed > 0
was_already_blind = R(m)=0 in main too — reported separately, never blamed on the departure
```

**Drill:**

```mermaid
sequenceDiagram
  autonumber
  participant UI as Console
  participant API as Sim engine
  participant DB as FalkorDB
  UI->>API: POST /api/simulate {person}
  API->>DB: main: create Sim node (status=running)
  API->>DB: GRAPH.COPY main to sim:drill-7f3
  API->>DB: sim: mark person departed, delete their KNOWS/OWNS edges
  API->>DB: sim: WCC islands, coverage, orphaned decisions, blindspots
  API->>DB: main: write Finding nodes (proof paths, severities) + metrics on Sim
  API-->>UI: findings + deltas + proof paths
  UI-->>UI: shatter animation (ghost node, island halos, counters)
```

**Surgery rule:** the person is *marked*, not deleted — artifacts (PRs, docs, reviews) keep attribution; only knowledge-carrying edges (`KNOWS`, `OWNS`) are removed in the clone. All coverage queries filter `status='active'`. Consequences flow through ordinary queries: we don't special-case the departed — reality simply no longer contains them.

**Heal:**

```mermaid
sequenceDiagram
  autonumber
  participant UI as Console
  participant API as Sim engine
  participant DB as FalkorDB
  UI->>API: POST /api/heal {plan_id}
  API->>DB: GRAPH.COPY main to sim:heal-9c1
  API->>DB: sim: apply the same departure as the drill
  API->>DB: sim: MERGE projected KNOWS {source: plan} per plan step
  API->>DB: sim: recompute WCC, coverage, findings
  API->>DB: main: write heal Sim + delta vs drill
  API-->>UI: bus factor 1 to 3, islands 4 to 0, resolved findings
  UI-->>UI: gold edges reconnect, counters animate
```

**Limits:** ≤ 32 concurrent worlds; `make clean-sims` prunes. Demo graph budget ≤ 3k nodes / ≤ 12k edges (12-month window + thresholds) → every drill < 10 s. Clone strategy: `GRAPH.COPY` (capability probed at startup via `/api/health`); fallback = replay the deterministic loader into the new graph (same graph by construction).

## 8. The agent, the trust layer, memory

```mermaid
flowchart TD
  Q["User question"] --> R["Resolve names to node ids<br/>fuzzy match + ambiguity check"]
  R -->|"ambiguous"| CF["Ask user to confirm"]
  CF --> R
  R -->|"no match"| U["outcome: unknown_person<br/>+ nearest candidates"]
  R --> P["LLM plans tool calls<br/>JSON only, schema-validated"]
  P --> E["Execute tool on a world<br/>reads via RO_QUERY"]
  E --> D{"Enough evidence?"}
  D -->|"no, up to 2 more calls"| P
  D -->|"yes"| A["Draft answer with row citations"]
  A --> V{"Validator: names, numbers,<br/>paths within this turn's evidence?"}
  V -->|"fail"| RP["One repair round<br/>offending tokens named"]
  RP --> V
  V -->|"fail again"| DG["Drop offending statements<br/>+ downgrade outcome"]
  V -->|"pass"| S["Set outcome shape"]
  DG --> S
  S --> M["Write Question node + CITED edges"]
  U --> M
  M --> O["Answer + citations + step log"]
```

**Tool catalogue — frozen at eight:**

| Tool | Engine | Returns | Why |
|---|---|---|---|
| `who_knows(module, limit=5)` | `KNOWS`/`OWNS` + review channel (`REVIEWED`→`PR`→`TOUCHES`) | Ranked people with evidence paths per channel | The primitive question; proves answers are traceable |
| `critical_people(limit=5)` | `algo.betweenness` on G_k + module PageRank + sole-knower tallies | Ranked persons + reason (bridge / breadth) | A fast prior — and it says so; ground truth comes from drilling |
| `knowledge_islands(world)` | `algo.WCC` on G_k | Components with modules but no active persons | The shatter, made measurable |
| `module_risk(module)` | Aggregation over `KNOWS`/`REVIEWED`/`DECIDED_BY` | Coverage, reviewers, doc safeties, orphaned decisions | Module-level verdict, not vibes |
| `simulate_departure(person)` | Sim engine (§7) | `sim_id`, findings, deltas | The differentiator — an action, not a report |
| `handover_plan(person, sim_id)` | Successor scoring + `algo.SPpaths` rationale | Ordered steps with named teachers + proof | Diagnosis must end in a plan |
| `heal_and_verify(plan_id)` | Sim engine (§7) | Before/after deltas, resolved findings | The proof, not the promise |
| `recall(query)` | `Question`/`CITED`/`Sim` traversal | Prior questions, findings, outcomes | Memory = more nodes |

**Core query templates** (production versions live in `agent/.../queries/*.cypher`; validated against FalkorDB's Cypher subset during implementation):

```cypher
// who_knows — params: $module_id, $limit
MATCH path = (p:Person {status:'active'})-[k:KNOWS|OWNS]->(m:Module {id:$module_id})
RETURN p.name AS person, type(k) AS channel, k.weight AS strength, k.source AS provenance,
       [n IN nodes(path) | coalesce(n.name, n.path)] AS hops
ORDER BY strength DESC LIMIT $limit
```

```cypher
// knowledge_islands — run inside a world graph
CALL algo.WCC({
  nodeLabels: ['Person','Module','Doc'],
  relationshipTypes: ['KNOWS','OWNS','DOCUMENTS']
}) YIELD node, componentId
WITH componentId, collect(node) AS members
WHERE none(x IN members WHERE x:Person AND x.status = 'active')
  AND any(x IN members WHERE x:Module)
RETURN componentId, [x IN members | coalesce(x.name, x.title)] AS stranded
```

```cypher
// handover rationale — params: $teacher_id, $module_id
MATCH (t:Person {id:$teacher_id}), (m:Module {id:$module_id})
CALL algo.SPpaths({
  sourceNode: t, targetNode: m, relTypes: ['KNOWS','OWNS'],
  weightProp: 'cost', relDirection: 'outgoing', pathCount: 3, maxLen: 4
}) YIELD path, pathWeight
RETURN [n IN nodes(path) | coalesce(n.name, n.path)] AS hops, pathWeight
```

**Outcome shapes** (first-class UX, shown as chips):

| Shape | Meaning |
|---|---|
| `answered_with_path` | Cites ≥1 path returned by the graph |
| `answered_from_memory` | Draws on persisted Questions/Sims/Findings |
| `not_in_graph` | No evidence existed; agent says so and explains why that matters |
| `unknown_person` | Name couldn't be resolved; nearest candidates offered |

**Validator rules, in order:** (1) extract names, numbers, path claims from the draft; (2) every name must appear in this turn's returned rows; (3) every number must equal an evidence value (or a whitelisted derived metric); (4) every path claim must match a returned path; (5) one repair round naming offending tokens, then drop + downgrade; (6) log every run for Show-your-work.

**Memory:** each turn writes `Question {text, outcome, created_at}` + `CITED`/`TRIGGERED` edges. Session bootstrap: the console (and MCP server) opens with a recall summary — last sim, open findings, bus-factor trend ("weakest node moved from X to Y", computed by diffing consecutive drill metrics). `recall` resolves names first, then token-overlap over `Question.text`. Deterministic, auditable, no vector store.

**LLM contract:** input = question + resolved ids + tool schemas + world context. Output = **JSON only** (`{tool, args}`), schema-validated server-side before execution. Temperature low. Env: `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`. Refusal instruction: if tools return no evidence, the model must say so and must not estimate.

**Benchmark vs baseline:** 10 frozen questions spanning lookups, review-channel, drill, decisions-at-risk, heal-verify, memory-recall, and three seeded refusals. Baseline = text-RAG over the same corpus (chunk docs + README + PR titles, embed, top-k, same LLM, no tools) — the thing a team actually does today. Scored: `correct · grounded (validator pass ratio) · refusal_correct`. Hypothesis stated in advance: baseline does fine on lookups, fails what-if/heal **by mechanism**, fabricates where BusFactor refuses.

## 9. FalkorDB utilization map

| Capability | Used for | Why it's the right tool |
|---|---|---|
| **Multigraph** (graph per what-if) | Drill worlds, heal worlds, filmstrip | Every hypothetical is a fully isolated graph in one instance — the product *is* worlds |
| **`GRAPH.COPY`** | Clone `main` → `sim:<id>` | Server-side atomic snapshot; copies indexes too; source stays queryable during copy |
| **`algo.WCC`** (`nodeLabels`/`relationshipTypes` filters) | Knowledge islands | Linear-time components; filters run it on G_k directly |
| **`algo.betweenness`** (`samplingSeed 42`) | Load-bearing people | Bridge detection on the knowledge view; seeded sampling = reproducible runs |
| **`algo.pageRank('Module','KNOWS')`** | Module criticality | Incoming-edge influence = how many people depend on a module; sizes nodes, weights plans |
| **`algo.SPpaths`** (`weightProp:'cost'`, `maxLen 4`) | Handover rationale | "Why this successor" as real shortest paths through strong knowledge edges |
| **`RO_QUERY`** | Every read | No read path can mutate anything |
| **Range indexes** | Entity resolution | Sub-ms lookups; verified via `GRAPH.EXPLAIN` |
| **`GRAPH.LIST` / `GRAPH.DELETE`** | Worlds housekeeping | Prune sims (`make clean-sims`) |

## 10. API, console, actions, MCP, deployment

**API surface:**

| Method | Path | World | Purpose |
|---|---|---|---|
| `GET` | `/api/graph?world=` | any | nodes + links + island groups for the canvas (`RO_QUERY`) |
| `GET` | `/api/worlds` | main | sim timeline metadata |
| `POST` | `/api/ask` | main | grounded Q&A; returns `steps[]` (SSE variant for streaming) |
| `POST` | `/api/simulate` | main→clone | run a drill `{person}`; writes findings + Sim |
| `POST` | `/api/plan` | main | plan for `{sim_id}`; writes Plan + Step nodes |
| `POST` | `/api/heal` | main→clone | apply `{plan_id}`, re-run same drill; writes heal Sim + delta |
| `POST` | `/api/actions` | — | `{plan_id, mode: preview/live, repo}` → GitHub issue + runbook PR draft |
| `GET` | `/api/memory` | main | questions/sims timeline + trend |
| `GET` | `/api/health` | — | db ping, graph stats, `GRAPH.COPY` capability probe |

**Console:**

```
┌────────────────────────────────────────────────────────────────┐
│  BusFactor        [world: main ▾]    [ Ask ]   [ Drill ▾ ]     │
├──────────────┬────────────────────────────────┬────────────────┤
│  Ask panel   │        graph canvas            │ Findings/Plan/ │
│  + outcome   │  (force-graph, world morphs)   │ Timeline tabs  │
│  chips       │                                │ (click to proof│
├──────────────┴────────────────────────────────┴────────────────┤
│  Show your work: tool · world · query · latency · rows         │
├────────────────────────────────────────────────────────────────┤
│  Worlds filmstrip:  main → drill-7f3 → heal-9c1                │
└────────────────────────────────────────────────────────────────┘
```

Style: persons coral · modules slate · docs teal · decisions violet · findings red; radius ← cached criticality; departed = dashed ghost; projected edges gold. Shatter = eased data swap + island halos; heal = gold fade-in + animated counters. Positions cached per world client-side (not in graph); render budget ≤ 5k nodes.

**Actions.** `POST /api/actions` renders the exact payload first (preview mode, the default); live mode requires explicit operator opt-in and a token scoped to a single operator-owned repo — **never a third-party repo** (I8). The payload: an issue with the plan checklist, evidence paths, and a linked `docs/runbooks/<module>.md` PR draft. This is the agent acting on connected data, not just reading it.

**MCP server.** `agent/busfactor/mcp_server.py` exposes the same 8 tools via `FastMCP` (stdio), so BusFactor is usable from Claude Code / Cursor — the exact "context for AI agents" pattern:

```json
{ "mcpServers": { "busfactor": {
    "command": "uv", "args": ["run", "python", "-m", "busfactor.mcp_server"],
    "env": { "FALKORDB_HOST": "localhost", "FALKORDB_PORT": "6379" } } } }
```

Read-only tools by default; `simulate`/`plan` allowed; `heal`/`actions` require env opt-in. (FalkorDB ships its own MCP server for raw graph access — ours exposes the *domain* tools; complementary, not a fork of it.)

**Deployment.** `docker compose up`: `falkordb` :6379 (volume) · `api` :8000 · `web` :5173. Make targets: `up · down · ingest · ingest-live · ask "…" · demo · bench · test · clean-sims · mcp`. Reproducibility contract: clean clone + `.env` + `make up && make ingest && make demo` reproduces the full arc locally. Live URL is optional — the local path is fully supported.

## 11. Non-goals

- **Not HR surveillance.** No performance scores, activity rankings, or "who works hardest". Findings are about *modules' exposure*, never a person's worth (no such fields exist in the schema).
- **Not attrition prediction.** Different data, different ethics; we don't claim it.
- **Not code search or git blame.** Git is one input; docs and decisions are equal citizens.
- **No LLM-authored Cypher, ever.** (I2.)
- **No writes to reality.** Plans, sims, and actions never mutate `main`'s observed history; GitHub writes are preview-first and scoped (I3, I8).

---

<div align="center"><sub><b>BusFactor</b> — lose anyone on Friday; ship on Monday.</sub></div>
