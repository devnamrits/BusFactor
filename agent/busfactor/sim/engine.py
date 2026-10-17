"""Drill and heal — the two verbs this product exists for.

A drill: clone the repo graph -> remove a person -> measure the delta ->
write the findings back as audit nodes (append-only; invariant I7).

A heal: clone again -> remove the same person -> apply the plan's
projected KNOWS edges -> re-run every metric. The heal world shows the
fix; it is not a claim, it is a measurement.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from .. import db
from . import audit, clone, diff, metrics, surgery
from .people import get_person
from .plan import get_plan


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_drill(person_ref: str, label: str | None = None, repo: str = "main") -> dict:
    t0 = time.time()
    person = get_person(person_ref, repo)
    main_snap = metrics.snapshot(repo)

    world = clone.new_world_id("drill")
    clone.clone_world(repo, world)
    surgery.remove_person(world, person["id"])
    sim_snap = metrics.snapshot(world)

    findings = diff.findings(main_snap, sim_snap, world, person)
    audit.attach_evidence(repo, findings, person["id"])

    sim_id = "sim-" + world.split(":", 1)[1]
    audit.write_simulation(
        repo, sim_id, "drill", label or f"{person['name']} departs",
        person["id"], world, sim_snap, findings,
    )
    clone.prune_worlds(repo)

    return {
        "sim_id": sim_id,
        "world": world,
        "person": person,
        "findings": findings,
        "before": metrics.summary(main_snap),
        "after": metrics.summary(sim_snap),
        "seconds": round(time.time() - t0, 2),
    }


_APPLY_STEP = (
    "MATCH (t:Person {id:$teacher}), (m:Module {id:$module}) "
    "WHERE NOT (t)-[:KNOWS|OWNS]->(m) "
    "CREATE (t)-[:KNOWS {source:'plan', weight:$weight, cost:$cost, commits:0, "
    "reviews:0, last_at:$now}]->(m)"
)


def run_heal(plan_id: str | None = None, repo: str = "main") -> dict:
    t0 = time.time()
    plan = get_plan(repo, plan_id)
    person = get_person(plan["target_person"], repo)
    main_snap = metrics.snapshot(repo)

    # the drill's shatter is the reference point the heal must undo
    d_rows = db.graph(repo).ro_query(
        "MATCH (s:Sim {id:$sid}) RETURN s.metrics_json", {"sid": plan["sim_id"]}
    ).result_set
    drill_metrics = json.loads(d_rows[0][0]) if d_rows and d_rows[0][0] else {}

    world = clone.new_world_id("heal")
    clone.clone_world(repo, world)
    surgery.remove_person(world, person["id"])

    for step in plan["steps"]:
        weight = 0.35 if step["kind"] == "resilience" else 0.40
        db.rw(
            world,
            _APPLY_STEP,
            {
                "teacher": step["teacher_id"],
                "module": step["module_id"],
                "weight": weight,
                "cost": round(1.0 - weight, 4),
                "now": _now(),
            },
        )
    applied = int(
        db.ro(world, "MATCH ()-[k:KNOWS {source:'plan'}]->() RETURN count(k)").result_set[0][0]
    )

    sim_snap = metrics.snapshot(world)
    remaining = diff.findings(main_snap, sim_snap, world, person)

    drill_rows = db.graph(repo).ro_query(
        "MATCH (s:Sim {id:$sid})-[:FOUND]->(f:Finding) "
        "RETURN f.id, f.kind, f.severity, f.claim, f.module_id ",
        {"sid": plan["sim_id"]},
    ).result_set
    drill_findings = [
        {"id": fid, "kind": kind, "severity": int(sev), "claim": claim, "module_id": mid}
        for fid, kind, sev, claim, mid in drill_rows
    ]

    # findings are keyed by (kind, module, claim) — ids embed the world name,
    # so they must not be compared across worlds.
    def fkey(f: dict) -> tuple:
        return (f["kind"], (f.get("module_id") or ""), f["claim"])

    remaining_keys = {fkey(f) for f in remaining}
    resolved = [f for f in drill_findings if fkey(f) not in remaining_keys]

    sim_id = "sim-" + world.split(":", 1)[1]
    audit.write_simulation(
        repo, sim_id, "heal", f"heal: {person['name']} · {plan['id']}",
        person["id"], world, sim_snap, remaining,
        extra={
            "plan_id": plan["id"],
            "applied_steps": applied,
            "resolved": len(resolved),
            "resolved_kinds": _histogram(f["kind"] for f in resolved),
            "remaining": len(remaining),
        },
    )
    db.rw(
        repo,
        "MATCH (pl:Plan {id:$id}) SET pl.status='healed', pl.healed_by=$sim",
        {"id": plan["id"], "sim": sim_id},
    )
    clone.prune_worlds(repo)

    return {
        "sim_id": sim_id,
        "world": world,
        "plan_id": plan["id"],
        "person": person,
        "applied_steps": applied,
        "resolved": resolved,
        "remaining": remaining,
        "before": metrics.summary(main_snap),
        "drill": drill_metrics,
        "after": metrics.summary(sim_snap),
        "seconds": round(time.time() - t0, 2),
    }


def _histogram(items) -> dict:
    out: dict[str, int] = {}
    for i in items:
        out[i] = out.get(i, 0) + 1
    return out
