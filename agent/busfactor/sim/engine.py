"""Drill and heal — the two verbs this product exists for.

A drill: clone main -> remove a person -> measure the delta -> write the
findings into main as audit nodes (append-only; invariant I7).

A heal: clone main -> remove the same person -> apply the plan's projected
KNOWS edges -> re-run every metric. The world shows the fix; it is not a
claim, it is a measurement.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from .. import db
from . import clone, diff, metrics, surgery
from .people import get_person

K = diff.K


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _summary(snap: dict) -> dict:
    return metrics.summary(snap)


def _attach_evidence(findings: list[dict], person_id: str) -> None:
    """Cite up to 3 recent PRs of the departing person per affected module."""
    mids = sorted({f["module_id"] for f in findings if f.get("module_id")})
    if not mids:
        return
    rows = db.graph().ro_query(
        "MATCH (p:Person {id:$pid})-[:AUTHORED]->(pr:PR)-[:TOUCHES]->(m:Module) "
        "WHERE m.id IN $mids "
        "RETURN m.id, pr.number, pr.title, pr.merged_at "
        "ORDER BY pr.merged_at DESC",
        {"pid": person_id, "mids": mids},
    ).result_set
    ev: dict[str, list] = {}
    for mid, num, title, at in rows:
        bucket = ev.setdefault(mid, [])
        if len(bucket) < 3:
            bucket.append({"pr": num, "title": title, "at": at})
    for f in findings:
        if f.get("module_id") in ev:
            f["proof"]["recent_prs"] = ev[f["module_id"]]


def _write_sim(
    sim_id: str,
    kind: str,
    label: str,
    target: str,
    world: str,
    snap: dict,
    findings: list[dict],
    extra: dict | None = None,
) -> None:
    props = {
        "id": sim_id,
        "kind": kind,
        "label": label,
        "target_person": target,
        "world": world,
        "status": "done",
        "created_at": _now(),
        "metrics_json": json.dumps(_summary(snap)),
    }
    if extra:
        db.rw(
            "main",
            "CREATE (s:Sim {id:$id, kind:$kind, label:$label, target_person:$target_person, "
            "world:$world, status:$status, created_at:$created_at, metrics_json:$metrics_json, "
            "delta_json:$delta})",
            {**props, "delta": json.dumps(extra)},
        )
    else:
        db.rw(
            "main",
            "CREATE (s:Sim {id:$id, kind:$kind, label:$label, target_person:$target_person, "
            "world:$world, status:$status, created_at:$created_at, metrics_json:$metrics_json})",
            props,
        )
    if not findings:
        return
    rows = [
        {
            "id": f["id"],
            "kind": f["kind"],
            "severity": f["severity"],
            "claim": f["claim"],
            "module_id": f.get("module_id") or "",
            "proof_json": json.dumps(f.get("proof") or {}),
            "created_at": props["created_at"],
        }
        for f in findings
    ]
    db.rw(
        "main",
        "UNWIND $rows AS r CREATE (f:Finding {id:r.id, kind:r.kind, severity:r.severity, "
        "claim:r.claim, module_id:r.module_id, proof_json:r.proof_json, created_at:r.created_at})",
        {"rows": rows},
    )
    db.rw(
        "main",
        "MATCH (s:Sim {id:$sid}) UNWIND $ids AS fid MATCH (f:Finding {id:fid}) "
        "CREATE (s)-[:FOUND]->(f)",
        {"sid": sim_id, "ids": [r["id"] for r in rows]},
    )
    about = [
        {"fid": f["id"], "mid": f["module_id"]}
        for f in findings
        if f.get("module_id")
    ]
    if about:
        db.rw(
            "main",
            "UNWIND $rows AS r MATCH (f:Finding {id:r.fid}), (m:Module {id:r.mid}) "
            "CREATE (f)-[:ABOUT]->(m)",
            {"rows": about},
        )


def run_drill(person_ref: str, label: str | None = None) -> dict:
    t0 = time.time()
    person = get_person(person_ref)
    main_snap = metrics.snapshot("main")
    world = clone.new_world_id("drill")
    clone.clone_world("main", world)
    surgery.remove_person(world, person["id"])
    sim_snap = metrics.snapshot(world)
    fs = diff.findings(main_snap, sim_snap, world, person)
    _attach_evidence(fs, person["id"])
    sim_id = "sim-" + world.split(":", 1)[1]
    _write_sim(
        sim_id,
        "drill",
        label or f"{person['name']} departs",
        person["id"],
        world,
        sim_snap,
        fs,
    )
    clone.prune_worlds()
    return {
        "sim_id": sim_id,
        "world": world,
        "person": person,
        "findings": fs,
        "before": _summary(main_snap),
        "after": _summary(sim_snap),
        "seconds": round(time.time() - t0, 2),
    }


_APPLY_STEP = (
    "MATCH (t:Person {id:$teacher}), (m:Module {id:$module}) "
    "WHERE NOT (t)-[:KNOWS|OWNS]->(m) "
    "CREATE (t)-[:KNOWS {source:'plan', weight:$weight, cost:$cost, commits:0, "
    "reviews:0, last_at:$now}]->(m)"
)


def _get_plan(plan_id: str | None) -> dict:
    if not plan_id or plan_id == "latest":
        rows = db.graph().ro_query(
            "MATCH (pl:Plan) RETURN pl.id, pl.target_person, pl.sim_id, pl.label "
            "ORDER BY pl.created_at DESC LIMIT 1"
        ).result_set
    else:
        rows = db.graph().ro_query(
            "MATCH (pl:Plan {id:$id}) RETURN pl.id, pl.target_person, pl.sim_id, pl.label",
            {"id": plan_id},
        ).result_set
    if not rows:
        raise ValueError("no plan found — run `plan` first")
    pid, target, sim_id, label = rows[0]
    steps = db.graph().ro_query(
        "MATCH (pl:Plan {id:$id})-[:HAS_STEP]->(st:Step) "
        "RETURN st.id, st.kind, st.order, st.module_id, st.teacher_id, st.note, st.proof_json "
        "ORDER BY st.order",
        {"id": pid},
    ).result_set
    return {
        "id": pid,
        "target_person": target,
        "sim_id": sim_id,
        "label": label,
        "steps": [
            {
                "id": sid,
                "kind": kind,
                "order": int(order),
                "module_id": mid,
                "teacher_id": tid,
                "note": note,
                "proof": json.loads(pj or "{}"),
            }
            for sid, kind, order, mid, tid, note, pj in steps
        ],
    }


def run_heal(plan_id: str | None = None) -> dict:
    t0 = time.time()
    plan = _get_plan(plan_id)
    person = get_person(plan["target_person"])
    main_snap = metrics.snapshot("main")

    world = clone.new_world_id("heal")
    clone.clone_world("main", world)
    surgery.remove_person(world, person["id"])

    applied = 0
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

    drill_rows = db.graph().ro_query(
        "MATCH (s:Sim {id:$sid})-[:FOUND]->(f:Finding) "
        "RETURN f.id, f.kind, f.severity, f.claim, f.module_id ",
        {"sid": plan["sim_id"]},
    ).result_set
    drill_findings = [
        {"id": fid, "kind": kind, "severity": int(sev), "claim": claim, "module_id": mid}
        for fid, kind, sev, claim, mid in drill_rows
    ]

    def fkey(f: dict) -> tuple:
        return (f["kind"], (f.get("module_id") or ""), f["claim"])

    remaining_keys = {fkey(f) for f in remaining}
    resolved = [f for f in drill_findings if fkey(f) not in remaining_keys]

    sim_id = "sim-" + world.split(":", 1)[1]
    _write_sim(
        sim_id,
        "heal",
        f"heal: {person['name']} · {plan['id']}",
        person["id"],
        world,
        sim_snap,
        remaining,
        extra={
            "plan_id": plan["id"],
            "applied_steps": applied,
            "resolved": len(resolved),
            "resolved_kinds": _histogram(f["kind"] for f in resolved),
            "remaining": len(remaining),
        },
    )
    db.rw(
        "main",
        "MATCH (pl:Plan {id:$id}) SET pl.status='healed', pl.healed_by=$sim",
        {"id": plan["id"], "sim": sim_id},
    )
    clone.prune_worlds()

    return {
        "sim_id": sim_id,
        "world": world,
        "plan_id": plan["id"],
        "person": person,
        "applied_steps": applied,
        "resolved": resolved,
        "remaining": remaining,
        "before": _summary(main_snap),
        "after": _summary(sim_snap),
        "seconds": round(time.time() - t0, 2),
    }


def _histogram(items) -> dict:
    out: dict[str, int] = {}
    for i in items:
        out[i] = out.get(i, 0) + 1
    return out
