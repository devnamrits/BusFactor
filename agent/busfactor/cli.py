"""BusFactor CLI — `python -m busfactor <command>`.

index · repos · ask · drill · plan · heal · status · people · sims · clean · demo

Every repo-scoped command takes `--repo <slug>`; the default "main" is the
pinned demo snapshot. `index` is how a new repo gets in.
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from . import db, memory, repos
from .agent import ask
from .sim import engine, make_plan
from .sim.people import get_person, list_people
from .tools.base import clean_ref, people_hint


def _rule(t: str) -> None:
    print(f"\n{t}\n" + "─" * min(72, len(t) + 8))


def _graph(args) -> str:
    return repos.graph_for(getattr(args, "repo", None) or "main")


def cmd_index(args) -> int:
    try:
        job = repos.connect(args.source, args.window_days)
    except (ValueError, RuntimeError) as e:
        print(f"error: {e}")
        return 1
    print(f"indexing {args.source} → slug '{job['slug']}' (graph {job['graph']})")
    last = None
    while True:
        r = repos.get_repo(job["slug"]) or {}
        line = f"{r.get('status', '?')}: {r.get('message', '')}".rstrip(": ")
        if line != last:
            print(f"  {line}")
            last = line
        if r.get("status") in ("ready", "error"):
            break
        time.sleep(1.5)
    if r.get("status") == "error":
        return 1
    print(
        f"ready — {r.get('people')} people · {r.get('modules')} modules · "
        f"{r.get('commits')} commits · snapshot {r.get('snapshot_sha')}"
    )
    print(f"try: busfactor ask --repo {job['slug']} \"who can't we lose?\"")
    return 0


def cmd_repos(_args) -> int:
    rows = repos.list_repos()
    _rule("INDEXED REPOS")
    for r in rows:
        print(
            f"  {r['slug']:<22} {r['status']:<8} {r['graph']:<28} "
            f"{r['people']:>3}p {r['modules']:>4}m  {r['url']}"
        )
    return 0


def cmd_ask(args) -> int:
    r = ask(" ".join(args.question), _graph(args))
    print(r["answer"])
    print(
        f"\n[{r['tool']} · {r['outcome']} · {r['seconds']}s · "
        f"validated={r['validated']}]"
    )
    if r["issues"]:
        print("issues:", r["issues"])
    if r["citations"]:
        print("cites:", ", ".join(c["label"] for c in r["citations"]))
    return 0


def cmd_drill(args) -> int:
    graph = _graph(args)
    try:
        person = get_person(clean_ref(" ".join(args.person)), graph)
    except ValueError as e:
        print(f"{e}. {people_hint(graph)}")
        return 1
    d = engine.run_drill(person["id"], repo=graph)
    _rule(f"DRILL — {person['name']} departs (world {d['world']})")
    print("before:", json.dumps(d["before"]))
    print("after: ", json.dumps(d["after"]))
    for f in d["findings"]:
        print(f"  [{f['severity']}] {f['kind']:<18} {f['claim']}")
    print(f"\n{d['seconds']}s · sim {d['sim_id']}")
    return 0


def cmd_plan(args) -> int:
    p = make_plan(args.sim, not args.no_resilience, _graph(args))
    _rule(f"PLAN {p['plan_id']} — {p['label']}")
    print("counts:", json.dumps(p["counts"]))
    for s in p["steps"]:
        print(f"  {s['order']:02d}. {s['module_name']:<24} → {s['teacher_name']:<18} {s['note']}")
    return 0


def cmd_heal(args) -> int:
    h = engine.run_heal(args.plan, _graph(args))
    _rule(f"HEAL — {h['plan_id']} applied in {h['world']}")
    print("applied steps:", h["applied_steps"])
    print("before:", json.dumps(h["before"]))
    print("after: ", json.dumps(h["after"]))
    print(f"resolved: {len(h['resolved'])} · remaining: {len(h['remaining'])}")
    for f in h["remaining"]:
        print(f"  REMAINS [{f['severity']}] {f['kind']}: {f['claim']}")
    return 0


def cmd_status(_args) -> int:
    _rule("STATUS")
    print("server :", "up" if db.ping() else "DOWN")
    print("graphs :", db.list_graphs())
    for r in repos.list_repos():
        print(
            f"  repo {r['slug']:<16} {r['status']:<8} memory "
            f"{json.dumps(memory.stats(r['graph']))}" if r["status"] == "ready" else
            f"  repo {r['slug']:<16} {r['status']:<8} {r['message']}"
        )
    return 0


def cmd_people(args) -> int:
    for p in list_people(_graph(args)):
        print(f"  {p['name']:<22} {p['commits']:>4} commits  {p['id']}")
    return 0


def cmd_sims(args) -> int:
    rows = db.ro(
        _graph(args),
        "MATCH (s:Sim) RETURN s.id, s.kind, s.label, s.world, s.created_at "
        "ORDER BY s.created_at",
    ).result_set
    for sid, kind, label, world, at in rows:
        print(f"  {at}  {kind:<6} {world:<18} {label}")
    return 0


def cmd_clean(args) -> int:
    graph = _graph(args)
    worlds = [
        w for (w,) in db.ro(graph, "MATCH (s:Sim) RETURN s.world").result_set if w
    ]
    db.rw(
        graph,
        "MATCH (n) WHERE n:Sim OR n:Finding OR n:Plan OR n:Step OR n:Question "
        "DETACH DELETE n",
    )
    for w in worlds:
        db.client().select_graph(w).delete()
    print(
        f"deleted {len(worlds)} world(s) + sim artifacts for '{args.repo}'; "
        "the snapshot stays loaded."
    )
    return 0


def cmd_demo(args) -> int:
    """The whole arc in one command: rank → drill → plan → heal."""
    from .tools import functions

    graph = _graph(args)
    _rule("1 · WHO CAN'T WE LOSE?")
    r = functions.critical_people(repo=graph)
    print(r["answer"])

    top = r["data"]["ranked"][0]
    _rule(f"2 · WHAT IF {top['name']} LEAVES?")
    r = functions.simulate_departure(top["id"], repo=graph)
    print(r["answer"])

    _rule("3 · HANDOVER PLAN")
    r = functions.handover_plan(r["data"]["sim_id"], repo=graph)
    print(r["answer"])

    _rule("4 · HEAL & VERIFY")
    r = functions.heal_and_verify(repo=graph)
    print(r["answer"])
    return 0


def _add_repo_flag(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "-r", "--repo", default="main",
        help="repo slug to work on (see `busfactor repos`)",
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="busfactor",
        description="Know who your team can't lose — and fix it before they leave.",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("index", help="index a GitHub repo or a local git clone")
    p.add_argument("source", help="https://github.com/owner/name or /path/to/clone")
    p.add_argument("--window-days", type=int, default=None)
    p.set_defaults(fn=cmd_index)

    sub.add_parser("repos", help="list indexed repos").set_defaults(fn=cmd_repos)

    p = sub.add_parser("ask", help="ask a question")
    p.add_argument("question", nargs="+")
    _add_repo_flag(p)
    p.set_defaults(fn=cmd_ask)

    p = sub.add_parser("drill", help="simulate a departure")
    p.add_argument("person", nargs="+")
    _add_repo_flag(p)
    p.set_defaults(fn=cmd_drill)

    p = sub.add_parser("plan", help="build a handover plan from the latest drill")
    p.add_argument("--sim", default=None)
    p.add_argument("--no-resilience", action="store_true")
    _add_repo_flag(p)
    p.set_defaults(fn=cmd_plan)

    p = sub.add_parser("heal", help="apply the latest plan in a clone world")
    p.add_argument("--plan", default=None)
    _add_repo_flag(p)
    p.set_defaults(fn=cmd_heal)

    sub.add_parser("status").set_defaults(fn=cmd_status)

    p = sub.add_parser("people")
    _add_repo_flag(p)
    p.set_defaults(fn=cmd_people)

    p = sub.add_parser("sims")
    _add_repo_flag(p)
    p.set_defaults(fn=cmd_sims)

    p = sub.add_parser("clean")
    _add_repo_flag(p)
    p.set_defaults(fn=cmd_clean)

    p = sub.add_parser("demo")
    _add_repo_flag(p)
    p.set_defaults(fn=cmd_demo)

    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
