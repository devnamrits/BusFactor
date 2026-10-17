"""Sim audit trail — every run leaves Sim and Finding nodes behind.

Append-only by construction: this module only creates. The repo graph's
observed facts stay exactly as the snapshot loaded them (invariant I7);
everything a drill or heal learns is written next to them, never over them.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from .. import db
from .metrics import summary


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def attach_evidence(repo: str, findings: list[dict], person_id: str) -> None:
    """Cite up to 3 recent PRs of the departing person per affected module."""
    mids = sorted({f["module_id"] for f in findings if f.get("module_id")})
    if not mids:
        return
    rows = db.graph(repo).ro_query(
        "MATCH (p:Person {id:$pid})-[:AUTHORED]->(pr:PR)-[:TOUCHES]->(m:Module) "
        "WHERE m.id IN $mids "
        "RETURN m.id, pr.number, pr.title, pr.merged_at "
        "ORDER BY pr.merged_at DESC",
        {"pid": person_id, "mids": mids},
    ).result_set
    evidence: dict[str, list] = {}
    for mid, num, title, at in rows:
        bucket = evidence.setdefault(mid, [])
        if len(bucket) < 3:
            bucket.append({"pr": num, "title": title, "at": at})
    for f in findings:
        if f.get("module_id") in evidence:
            f["proof"]["recent_prs"] = evidence[f["module_id"]]


def write_simulation(
    repo: str,
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
        "metrics_json": json.dumps(summary(snap)),
    }
    if extra:
        db.rw(
            repo,
            "CREATE (s:Sim {id:$id, kind:$kind, label:$label, target_person:$target_person, "
            "world:$world, status:$status, created_at:$created_at, metrics_json:$metrics_json, "
            "delta_json:$delta})",
            {**props, "delta": json.dumps(extra)},
        )
    else:
        db.rw(
            repo,
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
        repo,
        "UNWIND $rows AS r CREATE (f:Finding {id:r.id, kind:r.kind, severity:r.severity, "
        "claim:r.claim, module_id:r.module_id, proof_json:r.proof_json, created_at:r.created_at})",
        {"rows": rows},
    )
    db.rw(
        repo,
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
            repo,
            "UNWIND $rows AS r MATCH (f:Finding {id:r.fid}), (m:Module {id:r.mid}) "
            "CREATE (f)-[:ABOUT]->(m)",
            {"rows": about},
        )
