"""HTTP surface — thin, typed, and identical to every other front door.

Endpoints map 1:1 onto the tool catalogue plus the two graph views the
console needs (the knowledge map and the timeline). No business logic
lives here: it all belongs to `tools/` and `sim/`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import db, memory
from .agent import ask as agent_ask
from .config import settings
from .sim import engine, make_plan
from .sim.people import list_people

app = FastAPI(title="BusFactor", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # local console; the API is read-only outside sims
    allow_methods=["*"],
    allow_headers=["*"],
)

_GK = (
    "{nodeLabels:['Person','Module','Doc'], "
    "relationshipTypes:['KNOWS','OWNS','DOCUMENTS']}"
)


class AskBody(BaseModel):
    question: str


class DrillBody(BaseModel):
    person: str
    label: str | None = None


class PlanBody(BaseModel):
    sim_id: str | None = None
    include_resilience: bool = True


class HealBody(BaseModel):
    plan_id: str | None = None


def _count(query: str) -> int:
    try:
        return int(db.ro("main", query).result_set[0][0] or 0)
    except Exception:
        return 0


def _snapshot_sha() -> str:
    try:
        return hashlib.sha256(settings.snapshot_path.read_bytes()).hexdigest()[:12]
    except Exception:
        return ""


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": db.ping(),
        "graphs": db.list_graphs(),
        "snapshot_sha": _snapshot_sha(),
        "nodes": _count("MATCH (n) RETURN count(n)"),
        "edges": _count("MATCH ()-[r]->() RETURN count(r)"),
        "llm": settings.llm_enabled,
    }


@app.get("/api/people")
def people() -> list[dict]:
    return list_people()


@app.get("/api/overview")
def overview() -> dict:
    from .sim import metrics

    snap = metrics.snapshot("main")
    return {
        "summary": metrics.summary(snap),
        "coverage": snap["coverage"],
        "memory": {"stats": memory.stats(), "recent": memory.recent(6)},
        "worlds": db.sim_worlds(),
    }


@app.get("/api/timeline")
def timeline() -> dict:
    sims = db.ro(
        "main",
        "MATCH (s:Sim) RETURN s.id, s.kind, s.label, s.target_person, s.world, "
        "s.created_at, s.metrics_json, s.delta_json ORDER BY s.created_at",
    ).result_set
    plans = db.ro(
        "main",
        "MATCH (pl:Plan) OPTIONAL MATCH (pl)-[:HAS_STEP]->(st:Step) "
        "RETURN pl.id, pl.label, pl.status, pl.created_at, count(st) "
        "ORDER BY pl.created_at",
    ).result_set
    return {
        "sims": [
            {
                "id": sid,
                "kind": kind,
                "label": label,
                "target_person": target,
                "world": world,
                "created_at": at,
                "metrics": json.loads(mj or "{}"),
                "delta": json.loads(dj or "{}") if dj else {},
            }
            for sid, kind, label, target, world, at, mj, dj in sims
        ],
        "plans": [
            {
                "id": pid,
                "label": label,
                "status": status,
                "created_at": at,
                "steps": int(n or 0),
            }
            for pid, label, status, at, n in plans
        ],
        "worlds": db.sim_worlds(),
    }


@app.post("/api/ask")
def ask(body: AskBody) -> dict:
    if not body.question.strip():
        raise HTTPException(400, "empty question")
    return agent_ask(body.question)


@app.post("/api/drill")
def drill(body: DrillBody) -> dict:
    from .tools.functions import _people_hint
    from .sim.people import get_person

    try:
        person = get_person(body.person)
    except ValueError as e:
        raise HTTPException(404, f"{e}. {_people_hint()}") from e
    d = engine.run_drill(person["id"], body.label)
    counts: dict[str, int] = {}
    for f in d["findings"]:
        counts[f["kind"]] = counts.get(f["kind"], 0) + 1
    return {**d, "counts": counts}


@app.get("/api/findings")
def findings(sim_id: str | None = None) -> dict:
    if sim_id and sim_id != "latest":
        rows = db.ro(
            "main",
            "MATCH (s:Sim {id:$sid})-[:FOUND]->(f:Finding) "
            "RETURN s.id, f.id, f.kind, f.severity, f.claim, f.module_id, f.proof_json "
            "ORDER BY f.severity DESC, f.kind, f.module_id",
            {"sid": sim_id},
        ).result_set
    else:
        rows = db.ro(
            "main",
            "MATCH (s:Sim {kind:'drill'})-[:FOUND]->(f:Finding) "
            "WITH s, f ORDER BY s.created_at DESC "
            "RETURN s.id, f.id, f.kind, f.severity, f.claim, f.module_id, f.proof_json "
            "ORDER BY f.severity DESC, f.kind, f.module_id",
        ).result_set
    out = [
        {
            "sim_id": sid,
            "id": fid,
            "kind": kind,
            "severity": int(sev or 0),
            "claim": claim,
            "module_id": mid or None,
            "proof": json.loads(pj or "{}"),
        }
        for sid, fid, kind, sev, claim, mid, pj in rows
    ]
    return {"findings": out, "count": len(out)}


@app.post("/api/plan")
def plan(body: PlanBody) -> dict:
    try:
        return make_plan(body.sim_id, body.include_resilience)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/heal")
def heal(body: HealBody) -> dict:
    try:
        return engine.run_heal(body.plan_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.get("/api/memory")
def mem() -> dict:
    return {"stats": memory.stats(), "recent": memory.recent(30)}


@app.get("/api/graph")
def graph(world: str = "main") -> dict:
    w = world or "main"
    if w not in db.list_graphs():
        raise HTTPException(404, f"no such world: {w}")

    nrows = db.ro(
        w,
        "MATCH (n) WHERE n:Person OR n:Module OR n:Doc OR n:Decision "
        "RETURN labels(n)[0], n.id, coalesce(n.name, n.title, n.path), "
        "n.status, n.criticality",
    ).result_set
    nodes = [
        {
            "id": nid,
            "label": lab,
            "name": name or nid,
            "status": status or "",
            "criticality": round(float(crit or 0), 4),
        }
        for lab, nid, name, status, crit in nrows
    ]

    lrows = db.ro(
        w,
        "MATCH (a)-[r:KNOWS|OWNS|WROTE|DECIDED_BY|AFFECTS]->(b) "
        "RETURN a.id, type(r), b.id, r.weight, r.source",
    ).result_set
    links = [
        {
            "source": src,
            "target": dst,
            "type": typ,
            "weight": round(float(w2 or 0), 4) if w2 is not None else None,
            "plan": src2 == "plan",
        }
        for src, typ, dst, w2, src2 in lrows
    ]

    cres = db.ro(
        w, f"CALL algo.WCC({_GK}) YIELD node, componentId RETURN node.id, componentId"
    ).result_set
    comp = {nid: int(cid) for nid, cid in cres}

    sim_meta = None
    frows = db.ro(
        "main",
        "MATCH (s:Sim {world:$w})-[:FOUND]->(f:Finding) "
        "RETURN s.id, s.kind, s.label, f.id, f.kind, f.severity, f.module_id, f.claim, f.proof_json",
        {"w": w},
    ).result_set
    finding_list = []
    if frows:
        sim_meta = {"id": frows[0][0], "kind": frows[0][1], "label": frows[0][2]}
        for _sid, _sk, _sl, fid, fk, sev, mid, claim, pj in frows:
            finding_list.append(
                {
                    "id": fid,
                    "kind": fk,
                    "severity": int(sev or 0),
                    "module_id": mid or None,
                    "claim": claim,
                    "proof": json.loads(pj or "{}"),
                }
            )
    severity_by_module: dict[str, int] = {}
    for f in finding_list:
        if f["module_id"]:
            severity_by_module[f["module_id"]] = max(
                severity_by_module.get(f["module_id"], 0), f["severity"]
            )

    for n in nodes:
        n["component"] = comp.get(n["id"], -1)
        n["severity"] = severity_by_module.get(n["id"], 0)

    return {
        "world": w,
        "nodes": nodes,
        "links": links,
        "sim": sim_meta,
        "findings": finding_list,
        "counts": {"nodes": len(nodes), "links": len(links)},
    }


_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"
if _DIST.exists():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="web")
