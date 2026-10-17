# Benchmark results

_2026-10-17 06:05 UTC · Darwin arm64 · Python 3.12.12 · repo `main` · snapshot `4f980d091577`_

**12/12 tickets passed.**

| # | ticket | routed | outcome | validated | s | verdict |
|---|---|---|---|---|---|---|
| B1 | Who knows src/udf? | `who_knows` | `answered_with_path` | yes | 0.05 | pass |
| B2 | Who can we least afford to lose? | `critical_people` | `answered_with_path` | yes | 0.02 | pass |
| B3 | Where is knowledge stranded? | `knowledge_islands` | `answered_with_path` | yes | 0.01 | pass |
| B4 | Risk for src/udf | `module_risk` | `answered_with_path` | yes | 0.02 | pass |
| B5 | What if Roi Lipman leaves? | `simulate_departure` | `answered_with_path` | yes | 0.21 | pass |
| B6 | Build a handover plan | `handover_plan` | `answered_with_path` | yes | 0.02 | pass |
| B7 | Heal it and verify | `heal_and_verify` | `answered_with_path` | yes | 0.07 | pass |
| B8 | What did we decide about graphblas? | `recall` | `answered_from_memory` | yes | 0.01 | pass |
| B9 | What are the billing SLAs? | `recall` | `not_in_graph` | yes | 0.01 | pass |
| B10 | What if Jane Nobody leaves? | `simulate_departure` | `unknown_entity` | yes | 0.0 | pass |
| B11 | Hmm. | `recall` | `not_in_graph` | yes | 0.0 | pass |
| B12 | Who can we least afford to lose? | `recall` | `answered_from_memory` | yes | 0.0 | pass |

Routing is deterministic (no LLM configured), so this table is reproducible:
`make bench` resets sim artifacts and replays `data/benchmark.yml` in order.
B12 repeats B2 to prove the memory-first path; B9–B11 check that refusals
stay refusals instead of becoming guesses.
