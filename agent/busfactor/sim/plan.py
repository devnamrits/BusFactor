"""Handover plans: for every module at risk, pick the best next knower.

Candidates are active people who do not already know the module; they are
ranked by sibling coverage (weight on modules under the same top-level
tree, e.g. src/*) and by shared working history with the departing person.
Each step stores its rationale, so the console can show *why this person* —
never a black box.
"""

from __future__ import annotations

import json
import secrets
from collections import defaultdict
from datetime import UTC, datetime

from .. import db
from . import metrics
from .people import get_person

RESILIENCE_MIN_SEVERITY = 2  # rank pre-existing fragility like a real finding


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _prefix(module_id: str) -> str:
    name = module_id.removeprefix("m:")
    return name.split("/", 1)[0] if "/" in name else name


def _knowledge_path(repo: str, teacher_id: str, module_id: str) -> list[str]:
    """Shortest weighted bridge from a teacher's knowledge to a module.

    `algo.SPpaths` walks KNOWS edges in both directions, so it crosses the
    bipartite Person↔Module view: teacher → module they already carry →
    person who knows both → the target module. Empty when no bridge exists.
    """
    try:
        rows = db.ro(
            repo,
            "MATCH (t:Person {id:$t}), (m:Module {id:$m}) "
            "CALL algo.SPpaths({sourceNode: t, targetNode: m, "
            "relTypes:['KNOWS'], relDirection: 'both', weightProp: 'weight', "
            "pathCount: 1, maxLen: 5}) YIELD path, pathWeight "
            "RETURN [n IN nodes(path) | coalesce(n.name, n.path)] AS hops, pathWeight",
            {"t": teacher_id, "m": module_id},
        ).result_set
    except Exception:
        return []
    if not rows:
        return []
    hops = rows[0][0] or []
    return [str(h) for h in hops]


def _get_sim(repo: str, sim_id: str | None) -> dict:
    if not sim_id or sim_id == "latest":
        rows = db.ro(repo, 
            "MATCH (s:Sim {kind:'drill'}) RETURN s.id, s.target_person, s.label, s.metrics_json "
            "ORDER BY s.created_at DESC LIMIT 1"
        ).result_set
    else:
        rows = db.ro(repo, 
            "MATCH (s:Sim {id:$id}) RETURN s.id, s.target_person, s.label, s.metrics_json",
            {"id": sim_id},
        ).result_set
    if not rows:
        raise ValueError("no drill to plan from — run a drill first")
    sid, target, label, mjson = rows[0]
    return {
        "id": sid,
        "target_person": target,
        "label": label,
        "metrics": json.loads(mjson or "{}"),
    }


def _targets_from_findings(repo: str, sim_id: str) -> dict[str, dict]:
    rows = db.ro(repo, 
        "MATCH (s:Sim {id:$sid})-[:FOUND]->(f:Finding) "
        "WHERE f.module_id IS NOT NULL AND f.module_id <> '' "
        "RETURN f.kind, f.severity, f.claim, f.module_id "
        "ORDER BY f.severity DESC, f.kind, f.module_id",
        {"sid": sim_id},
    ).result_set
    targets: dict[str, dict] = {}
    for kind, severity, claim, mid in rows:
        if kind in ("sole_knower_lost", "module_blind", "coverage_thin") and mid not in targets:
            targets[mid] = {"kind": kind, "severity": int(severity), "claim": claim}
    return targets


def _resilience_targets(repo: str, targets: dict[str, dict], dep: dict) -> dict[str, dict]:
    """Pre-existing single-knower modules (visible today, not caused by the drill)."""
    snap = metrics.snapshot(repo)
    out = dict(targets)
    for mid, info in snap["coverage"].items():
        if mid in out or len(info["knowers"]) != 1:
            continue
        out[mid] = {
            "kind": "resilience",
            "severity": RESILIENCE_MIN_SEVERITY,
            "claim": (
                f"{info['name']} lives on a single knower today "
                f"({info['knowers'][0]['name']}) — pre-existing fragility, "
                f"not caused by {dep['name']}'s departure"
            ),
        }
    return out


def get_plan(repo: str, plan_id: str | None) -> dict:
    """Load a plan + its ordered steps. The engine, API and MCP all share this."""
    if not plan_id or plan_id == "latest":
        rows = db.ro(repo, 
            "MATCH (pl:Plan) RETURN pl.id, pl.target_person, pl.sim_id, pl.label "
            "ORDER BY pl.created_at DESC LIMIT 1"
        ).result_set
    else:
        rows = db.ro(repo, 
            "MATCH (pl:Plan {id:$id}) RETURN pl.id, pl.target_person, pl.sim_id, pl.label",
            {"id": plan_id},
        ).result_set
    if not rows:
        raise ValueError("no plan found — run `plan` first")
    pid, target, sim_id, label = rows[0]
    steps = db.ro(repo, 
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


def make_plan(
    sim_id: str | None = None, include_resilience: bool = True, repo: str = "main"
) -> dict:
    sim = _get_sim(repo, sim_id)
    dep = get_person(sim["target_person"], repo)

    targets = _targets_from_findings(repo, sim["id"])
    if include_resilience:
        targets = _resilience_targets(repo, targets, dep)

    # ---- candidate landscape (computed in Python; the graph is small) ------
    edges = db.ro(repo, 
        "MATCH (p:Person {status:'active'})-[k:KNOWS]->(m:Module) "
        "RETURN p.id, p.name, m.id, m.name, k.weight"
    ).result_set
    by_person: dict[str, dict[str, float]] = defaultdict(dict)
    pname: dict[str, str] = {}
    mname: dict[str, str] = {}
    for pid, pn, mid, mn, w in edges:
        by_person[pid][mid] = float(w or 0.0)
        pname[pid] = pn
        mname[mid] = mn
    dep_edges = dict(by_person.get(dep["id"], {}))

    snap_main = metrics.snapshot(repo)

    token = secrets.token_hex(2)
    plan_id = f"plan-{token}"
    steps: list[dict] = []
    order = 0
    load: dict[str, int] = defaultdict(int)  # teacher_id -> steps so far

    ranked_targets = sorted(
        targets.items(), key=lambda kv: (-kv[1]["severity"], mname.get(kv[0], kv[0]))
    )
    for mid, t in ranked_targets:
        existing = {
            k["id"] for k in snap_main["coverage"].get(mid, {"knowers": []})["knowers"]
        }
        want = 2 if t["kind"] in ("sole_knower_lost", "module_blind") else 1
        prefix = _prefix(mid)

        cands = []
        for pid, medges in by_person.items():
            if pid == dep["id"] or pid in existing:
                continue
            sib = sum(w for m2, w in medges.items() if m2 != mid and _prefix(m2) == prefix)
            sib_names = sorted(
                mname.get(m2, m2) for m2 in medges if m2 != mid and _prefix(m2) == prefix
            )
            shared = [m2 for m2 in medges if m2 in dep_edges and m2 != mid]
            shared_score = sum(min(medges[m2], dep_edges[m2]) for m2 in shared)
            score = sib + 0.5 * shared_score
            cands.append(
                {
                    "id": pid,
                    "name": pname[pid],
                    "score": score,
                    "sib_mass": sib,
                    "sib_modules": sib_names,
                    "shared": sorted(mname.get(m2, m2) for m2 in shared),
                }
            )
        # spread the handover: a teacher already carrying several picks pays a
        # small load penalty so coverage widens instead of piling on one pair.
        chosen = sorted(
            cands, key=lambda c: (-round(c["score"] - 0.5 * load[c["id"]], 4), c["name"])
        )[:want]
        for c in chosen:
            load[c["id"]] += 1
        if not chosen:
            continue

        for c in chosen:
            order += 1
            if c["sib_mass"] > 0:
                why = (
                    f"carries {len(c['sib_modules'])} sibling module(s) under "
                    f"{prefix}/ (mass {c['sib_mass']:.2f})"
                )
            else:
                why = "generalist — widest coverage in the graph"
            if c["shared"]:
                why += f"; co-worked with {dep['name']} on {', '.join(c['shared'][:2])}"
            path_hops = _knowledge_path(repo, c["id"], mid)
            steps.append(
                {
                    "id": f"step-{token}-{order:02d}",
                    "kind": t["kind"],
                    "order": order,
                    "module_id": mid,
                    "module_name": mname.get(mid, mid),
                    "teacher_id": c["id"],
                    "teacher_name": c["name"],
                    "note": why,
                    "proof": json.dumps(
                        {
                            "sibling_modules": c["sib_modules"],
                            "shared_with_departed": c["shared"],
                            "sibling_mass": round(c["sib_mass"], 4),
                            "knowledge_path": path_hops,
                        }
                    ),
                }
            )

    # ---- persist ------------------------------------------------------------
    db.rw(
        repo,
        "CREATE (pl:Plan {id:$id, label:$label, target_person:$target, sim_id:$sim, "
        "status:'open', created_at:$now})",
        {
            "id": plan_id,
            "label": f"handover plan for {dep['name']}'s modules",
            "target": dep["id"],
            "sim": sim["id"],
            "now": _now(),
        },
    )
    db.rw(
        repo,
        "UNWIND $rows AS r CREATE (st:Step {id:r.id, kind:r.kind, order:r.order, "
        "module_id:r.module_id, teacher_id:r.teacher_id, note:r.note, proof_json:r.proof})",
        {"rows": steps},
    )
    db.rw(
        repo,
        "MATCH (pl:Plan {id:$id}) UNWIND $ids AS sid MATCH (st:Step {id:sid}) "
        "CREATE (pl)-[:HAS_STEP]->(st)",
        {"id": plan_id, "ids": [s["id"] for s in steps]},
    )
    db.rw(
        repo,
        "UNWIND $rows AS r MATCH (st:Step {id:r.sid}), (m:Module {id:r.mid}) "
        "CREATE (st)-[:COVERS]->(m)",
        {"rows": [{"sid": s["id"], "mid": s["module_id"]} for s in steps]},
    )
    db.rw(
        repo,
        "UNWIND $rows AS r MATCH (st:Step {id:r.sid}), (p:Person {id:r.pid}) "
        "CREATE (st)-[:TEACHER]->(p)",
        {"rows": [{"sid": s["id"], "pid": s["teacher_id"]} for s in steps]},
    )
    db.rw(
        repo,
        "MATCH (pl:Plan {id:$id}), (s:Sim {id:$sim}) CREATE (pl)-[:BASED_ON]->(s)",
        {"id": plan_id, "sim": sim["id"]},
    )

    return {
        "plan_id": plan_id,
        "label": f"handover plan for {dep['name']}'s modules",
        "target": dep,
        "sim_id": sim["id"],
        "steps": steps,
        "counts": {
            "steps": len(steps),
            "modules": len(ranked_targets),
            "critical": sum(1 for s in steps if s["kind"] in ("sole_knower_lost", "module_blind")),
            "thin": sum(1 for s in steps if s["kind"] == "coverage_thin"),
            "resilience": sum(1 for s in steps if s["kind"] == "resilience"),
        },
    }
