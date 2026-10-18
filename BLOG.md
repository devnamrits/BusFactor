# Your team's bus factor is a graph problem

*How BusFactor models who-knows-what in a repository — and lets you rehearse losing a teammate before it happens.*

Every long-lived codebase has a quiet asymmetry: activity is easy to measure, knowledge is not. Your dashboard can tell you who commits the most lines. It cannot tell you that one person is the only human who has ever touched *why* the high-level REST client works the way it does — or that an architecture decision points at a module whose last maintainer just handed in their notice.

The bus factor is the number of people who can vanish before a project stalls. Most teams treat it as a joke with a number attached, because every tool they have measures the past: commits, lines, review counts. None of those numbers answer the question that actually keeps a tech lead up at night:

**If this person leaves tomorrow, what breaks — and what do we do about it?**

BusFactor is a working answer. You point it at a repository; it ingests the history — commits, pull requests, docs, decisions — into a knowledge graph on FalkorDB; and then it gives you three verbs: *ask*, *drill*, *heal*.

## Knowledge is a relationship, not a number

A spreadsheet can count your commits. It can't represent the fact that **shared work is what makes knowledge transferable**: two people who have touched the same module, reviewed the same pull requests, or written the same docs share something that a solo contributor doesn't. That's a graph, and modeling it as anything else is an exercise in losing information at exactly the moment it matters.

The model is small on purpose. Nodes: **People**, **Modules**, **Pull Requests**, **Docs**, **Decisions** — plus the question/answer nodes that make the assistant's memory auditable. Edges: `KNOWS` (weighted), `AUTHORED`, `REVIEWED`, `TOUCHES`, `WROTE`, `DECIDED_BY`, `AFFECTS`, `OWNS`.

The interesting edge is `KNOWS`. It isn't a boolean; it decays and varies:

```
weight = 0.50 * commit_share   # this person's commits / all commits in the module
       + 0.30 * review_share   # reviews on PRs that touch the module
       + 0.20 * recency        # exponential decay since last activity
```

A "module" here is a top-two-level path in the repo (`client/rest-high-level`, `modules/parent-join`), deliberately not a file, because files are noise and modules are where decisions live. Trees like `docs/`, `build/`, `deps/` and `.github/` are treated as plumbing and excluded — they hold prose and process, not code knowledge. Thresholds are pinned and recorded with every snapshot: modules need at least 3 commits in the window to be tracked, contributors need a meaningful share of a module to be recorded as knowing it, and the raw history window is configurable (up to a decade, if you're pointing it at Elasticsearch).

Ingestion is deterministic — no LLM touches the data. The same clone at the same commit produces a byte-identical snapshot, with the hash embedded in the graph metadata so consumers can verify exactly what they loaded. If ingestion hallucinated, everything downstream would be theater; so ingestion doesn't get to hallucinate.

## The three verbs

**Ask.** A plain-language question ("who can we least afford to lose?") gets routed to one of nine read-only graph tools: `who_knows`, `critical_people`, `knowledge_islands`, `module_risk`, `simulate_departure`, `handover_plan`, `heal_and_verify`, `recall`, and `relations`. An LLM can pick *which* read to run when it's configured — but it never writes Cypher, never touches the data, and the product is fully functional with it switched off. Deterministic pattern matching is the always-on fallback. Every numeric claim in an answer is validated against the tool's returned data before the answer renders; the console shows a "numbers verified" badge, and the foot of every answer says who did the computing: *the graph computed this answer; the LLM only picked which read to run.*

**Drill.** The question no dashboard can answer — *what actually breaks if this person leaves?* — gets answered the only honest way: by removing them. BusFactor copies the main graph into a throwaway world (`GRAPH.COPY`), performs the surgery there, recomputes every metric on the real graph engine, and diffs the two worlds into findings, each with a proof:

- `sole_knower_lost` — a module just lost its last recorded knower
- `coverage_thin` — the survivors are down to the minimum
- `orphaned_decision` — a decision now references knowledge nobody in the team carries

The real graph is never touched. On the elasticsearch history we loaded (194 people, 80 modules, 596 knowledge edges, 44 decisions), drilling one engineer takes 0.3 seconds and produces the sentence the whole project exists to say: *the high-level REST client loses its last recorded knower.*

**Heal.** A plan without verification is a suggestion. So BusFactor drafts a handover plan — for each finding, a teacher, chosen by sibling-module mass and co-working history — that names *how* the transfer would work, previews it as a real work order, and then re-runs the disaster with the fix in place. The healed copy reports deltas, not vibes: stranded components 1 → 0, zero-knower modules 1 → 0, *1 of 1 drill findings resolved · applied 2 projected ownership edges*. And it lists what it could not fix, because a repair report that can't say "remaining: 3 orphaned decisions" isn't a report.

## Where FalkorDB is doing the heavy lifting

The what-if machinery is native to the database, not simulated in Python: a drill is literally a second graph, and a heal is a third. That means the risk model is recomputed by the same engine that serves production queries — no second, lying implementation in application code.

Connected components come from `algo.WCC`: after a departure, anything no longer connected to the team's main knowledge component is stranded. That's what "knowledge islands" means operationally.

For handover planning, we use the graph to find *bridges* — the shortest weighted path between a candidate teacher and the losing module, walking shared knowledge:

```cypher
CALL algo.SPpaths({
  sourceNode: $teacher, targetNode: $departed,
  relTypes: ['KNOWS'], relDirection: 'both',
  weightProp: 'weight', pathCount: 1
})
```

A real finding from the Elasticsearch graph: `Rene Groeschke → rest-api-spec → Benjamin Trent → client/rest-high-level`. The plan doesn't say "pair Rene with Benjamin because of seniority"; it says *these two are connected through shared work on the REST API spec, and that's the transfer channel*. (Small gotcha we hit and now document: on this bipartite person/module view, `relDirection:'outgoing'` returns zero rows for SPpaths; `'both'` is what works.)

**What we rejected, honestly.** The first version of the criticality score used PageRank. On a bipartite person–module view it degenerated to near-uniform weights — everyone's connected to everything, so the algorithm measured the graph's shape rather than the team's dependency. We replaced it with a direct knowledge-mass rollup: each person's importance is the sum of the `KNOWS` weights they hold. Less glamorous, actually correct, and explainable in one sentence on camera.

## Honesty is a feature

The hardest part of an assistant like this is not making it answer; it's making it *refuse*. Three mechanisms keep it honest:

1. **A fixed tool catalogue.** The model can only choose among the nine reads; free-form Cypher generation is banned by design (audit, injection safety, and the small matter of not letting a language model invent join logic).
2. **A number validator.** Every answer template is built from tool data, and a final pass checks that each numeric claim appears in the returned data. Fabricated figures don't render.
3. **Four outcome shapes.** Answers are `answered_with_path`, `answered_from_memory`, `not_in_graph`, or `error` — and refusals are treated as demonstrations, not failures.

My favorite test of that last point came from a real user question about a real Elasticsearch contributor: *"What does István Zoltán Szabó carry?"* The interesting answer — the honest one — is:

> István Zoltán Szabó has no recorded module knowledge. What the graph does hold: 2 doc page(s) they wrote (e.g. "Reimplementing and extending the smartcn analyzer"). Docs and build trees are plumbing in this index, not knowledge modules; scattered code touches stay below the significance floor.

He has 454 commits in the window — but 1,063 of the 1,079 files he touched live under `docs/`, which this index deliberately treats as plumbing, and his handful of code commits amount to a rounding error inside enormous modules. The graph's first answer used to be a bare "no recorded module knowledge," which reads like a bug. Now it says exactly what it knows, exactly what it doesn't, and why — and every "why" is clickable down to the two documentation pages that are his real trail.

That's the standard we hold the whole product to: **the assistant is allowed to know things; it is not allowed to guess.**

## What real repositories look like

We ship a benchmark (12 questions, from factual lookups to adversarial what-ifs) and run it on every change; the honest baseline — a naive retrieval demo — scores zero on anything that requires simulating a removal, because there's nothing to retrieve: the answer doesn't exist until the graph computes it.

On the Elasticsearch history: bus factor **1** — one departure strands knowledge. On our own repo, drilling our most critical contributor produces 20 findings across three channels, a 31-step handover plan with five teachers, and a heal that takes stranded components from 11 to 0 and the bus factor from 1 to 2 — leaving exactly three orphaned decisions *unresolved and reported as such*.

## Limitations, stated plainly

- **Reviews need a token.** The knowledge weight has a review component; without a GitHub token (the default), it degrades gracefully to commits + recency. The graph says what it had.
- **Docs are excluded from modules by design.** A documentation-heavy contributor can carry enormous real value and zero module knowledge. The graph is explicit about this instead of pretending otherwise.
- **Identity is a heuristic.** Author strings that normalize to the same name (case/space/punctuation-insensitive) collapse into the most active record; every merge is logged and auditable.
- **Headline numbers are for reading together.** A drill can lower a module below one knower — at which point it stops counting as a "minimum knowers" module entirely and the headline bus factor can even *rise*. Every surface therefore shows zero-knower modules and stranded components next to the bus factor. If a tool showed you only one number, you should distrust it.

## Run it on your repo

```bash
docker compose up -d            # falkordb + api + web
make ingest                     # load the pinned demo data
# console on http://localhost:5173 · API on http://localhost:8000
# then: paste any git URL (or a local clone path) into the console and index it
```

The same tool surface is exposed over MCP, so an agent can call it directly:

```bash
claude mcp add busfactor -- uv run python -m busfactor.mcp_server
```

Every answer carries its path, every risk carries its fix, and every simulated world is a copy you can throw away. Because losing people is inevitable. Losing their knowledge doesn't have to be.
