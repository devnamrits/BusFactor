"""BusFactor CLI — `python -m busfactor <command>`.

ask · drill · plan · heal · status · people · sims · clean · demo
"""

from __future__ import annotations

import argparse
import json
import sys

from . import db, memory
from .agent import ask
from .sim import engine, make_plan
from .sim.people import list_people


def _rule(t: str) -> None:
    print(f"\n{t}\n" + "─" * min(72, len(t) + 8))


def cmd_ask(args) -> int:
    r = ask(" ".join(args.question))
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
    from .tools.functions import _people_hint, _clean_ref
    from .sim.people import get_person
    try:
        person = get_person(_clean_ref(" ".join(args.person)))
    except ValueError as e:
        print(f"{e}. {_people_hint()}")
        return 1
    d = engine.run_drill(person["id"])
    _rule(f"DR DILL — {person['name']} departs (world {d['world']})")
    print("before:", json.dumps(d["before"]))
    print("after: ", json.dumps(d["after"]))
    for f in d["findings"]:
        print(f"  [{f['severity']}] {f['kind']:<18} {f['claim']}")
    print(f"\n{d['seconds']}s · sim {d['sim_id']}")
    return 0


def cmd_plan(args) -> int:
    p = make_plan(args.sim, not args.no_resilience)
    _rule(f"PLAN {p['plan_id']} — {p['label']}")
    print("counts:", json.dumps(p["counts"]))
    for s in p["steps"]:
        print(f"  {s['order']:02d}. {s['module_name']:<24} → {s['teacher_name']:<18} {s['note']}")
    return 0


def cmd_heal(args) -> int:
    h = engine.run_heal(args.plan)
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
    print("memory :", json.dumps(memory.stats()))
    return 0


def cmd_people(_args) -> int:
    for p in list_people():
        print(f"  {p['name']:<22} {p['commits']:>4} commits  {p['id']}")
    return 0


def cmd_sims(_args) -> int:
    rows = db.ro(
        "main",
        "MATCH (s:Sim) RETURN s.id, s.kind, s.label, s.world, s.created_at "
        "ORDER BY s.created_at",
    ).result_set
    for sid, kind, label, world, at in rows:
        print(f"  {at}  {kind:<6} {world:<18} {label}")
    return 0


def cmd_clean(_args) -> int:
    db.rw(
        "main",
        "MATCH (n) WHERE n:Sim OR n:Finding OR n:Plan OR n:Step OR n:Question "
        "DETACH DELETE n",
    )
    for w in db.sim_worlds():
        db.client().select_graph(w).delete()
    print("sim artifacts + worlds deleted; the snapshot stays loaded.")
    return 0


def cmd_demo(_args) -> int:
    """The whole arc in one command: rank → drill → plan → heal."""
    from .tools import functions

    _rule("1 · WHO CAN'T WE LOSE?")
    r = functions.critical_people()
    print(r["answer"])

    top = r["data"]["ranked"][0]
    _rule(f"2 · WHAT IF {top['name']} LEAVES?")
    r = functions.simulate_departure(top["id"])
    print(r["answer"])

    _rule("3 · HANDOVER PLAN")
    r = functions.handover_plan(r["data"]["sim_id"])
    print(r["answer"])

    _rule("4 · HEAL & VERIFY")
    r = functions.heal_and_verify()
    print(r["answer"])
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="busfactor",
        description="Know who your team can't lose — and fix it before they leave.",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("ask", help="ask a question")
    p.add_argument("question", nargs="+")
    p.set_defaults(fn=cmd_ask)

    p = sub.add_parser("drill", help="simulate a departure")
    p.add_argument("person", nargs="+")
    p.set_defaults(fn=cmd_drill)

    p = sub.add_parser("plan", help="build a handover plan from the latest drill")
    p.add_argument("--sim", default=None)
    p.add_argument("--no-resilience", action="store_true")
    p.set_defaults(fn=cmd_plan)

    p = sub.add_parser("heal", help="apply the latest plan in a clone world")
    p.add_argument("--plan", default=None)
    p.set_defaults(fn=cmd_heal)

    sub.add_parser("status").set_defaults(fn=cmd_status)
    sub.add_parser("people").set_defaults(fn=cmd_people)
    sub.add_parser("sims").set_defaults(fn=cmd_sims)
    sub.add_parser("clean").set_defaults(fn=cmd_clean)
    sub.add_parser("demo").set_defaults(fn=cmd_demo)

    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
