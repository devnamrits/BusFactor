"""The honesty benchmark — frozen tickets, replayed through the real agent loop.

`make bench` (a.k.a. `python -m busfactor.benchmark`) resets the sim
artifacts, runs every ticket in `data/benchmark.yml` in order, and checks:

  1. routing   — did the planner pick the intended tool?
  2. outcome   — answered vs the exact refusal shape?
  3. grounding — did every number in the answer survive the validator?

Results land in `results.md` at the repo root. The interesting column is the
verdict on refusals (B9–B11): an agent that refuses correctly is doing its job.
"""

from __future__ import annotations

import platform
import sys
import time
from datetime import UTC, datetime

import yaml

from . import db
from .agent import ask
from .config import ROOT, settings
from .sim.clone import prune_worlds

QUESTIONS = ROOT / "data" / "benchmark.yml"
RESULTS = ROOT / "results.md"
ANSWERED = {"answered_with_path", "answered_from_memory"}


def _reset(repo: str) -> None:
    """Deterministic starting line: no sims, no findings, no question log."""
    worlds = [w for (w,) in db.ro(repo, "MATCH (s:Sim) RETURN s.world").result_set if w]
    db.rw(
        repo,
        "MATCH (n) WHERE n:Sim OR n:Finding OR n:Plan OR n:Step OR n:Question "
        "DETACH DELETE n",
    )
    for w in worlds:
        try:
            db.client().select_graph(w).delete()
        except Exception:
            pass


def _check(case: dict, r: dict) -> tuple[bool, list[str]]:
    problems = []
    if r["tool"] != case["tool"]:
        problems.append(f"routed to {r['tool']}, wanted {case['tool']}")
    want = case["outcome"]
    if want == "answered":
        if r["outcome"] not in ANSWERED:
            problems.append(f"outcome {r['outcome']}, wanted an answer")
    elif r["outcome"] != want:
        problems.append(f"outcome {r['outcome']}, wanted {want}")
    if r["outcome"] in ANSWERED and not r["validated"]:
        problems.append("validator: " + "; ".join(r["issues"]))
    return (not problems), problems


def run(repo: str = "main") -> int:
    cases = yaml.safe_load(QUESTIONS.read_text(encoding="utf-8"))
    # the benchmark measures the deterministic contract — an LLM router in
    # .env must not make `make bench` flaky or provider-dependent
    settings.llm_base_url = ""
    _reset(repo)
    rows = []
    passed = 0

    print(f"benchmark · {len(cases)} tickets · repo '{repo}'")
    for case in cases:
        t0 = time.time()
        r = ask(case["question"], repo)
        ok, problems = _check(case, r)
        passed += ok
        mark = "pass" if ok else "FAIL"
        print(f"  {case['id']:<4} {mark:<4} {r['tool']:<18} {r['outcome']:<22} {time.time()-t0:.2f}s")
        for p in problems:
            print(f"        — {p}")
        rows.append(
            {
                "id": case["id"],
                "question": case["question"],
                "want_tool": case["tool"],
                "tool": r["tool"],
                "outcome": r["outcome"],
                "validated": r["validated"],
                "seconds": r["seconds"],
                "ok": ok,
                "problems": problems,
            }
        )

    sha = ""
    try:
        import hashlib

        sha = hashlib.sha256(settings.snapshot_path.read_bytes()).hexdigest()[:12]
    except Exception:
        pass

    lines = [
        "# Benchmark results",
        "",
        (
            f"_{datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')} · "
            f"{platform.system()} {platform.machine()} · Python {platform.python_version()} · "
            f"repo `{repo}` · snapshot `{sha}`_"
        ),
        "",
        f"**{passed}/{len(rows)} tickets passed.**",
        "",
        "| # | ticket | routed | outcome | validated | s | verdict |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['id']} | {row['question']} | `{row['tool']}` | `{row['outcome']}` | "
            f"{'yes' if row['validated'] else 'no'} | {row['seconds']} | "
            f"{'pass' if row['ok'] else 'FAIL — ' + '; '.join(row['problems'])} |"
        )
    lines += [
        "",
        "Routing is deterministic (no LLM configured), so this table is reproducible:",
        "`make bench` resets sim artifacts and replays `data/benchmark.yml` in order.",
        "B12 repeats B2 to prove the memory-first path; B9–B11 check that refusals",
        "stay refusals instead of becoming guesses.",
        "",
    ]
    RESULTS.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} passed · wrote {RESULTS.relative_to(ROOT)}")
    prune_worlds(repo)
    return 0 if passed == len(rows) else 1


def main(argv: list[str] | None = None) -> int:
    args = [a for a in (argv if argv is not None else sys.argv[1:]) if a != "run"]
    repo = "main"
    if "--repo" in args:
        repo = args[args.index("--repo") + 1]
    return run(repo)


if __name__ == "__main__":
    sys.exit(main())
