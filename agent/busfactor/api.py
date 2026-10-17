"""HTTP surface — thin, typed, and identical to every other front door.

Endpoints map onto the tool catalogue plus the two graph views the console
needs (the knowledge map and the timeline). Repo-scoped calls take a `repo`
slug and resolve it through the registry; no business logic lives here.

    GET  /api/health            server + store status
    GET  /api/repos             indexed repos + ingest defaults
    POST /api/repos             index a GitHub URL or a local git clone
    GET  /api/config            runtime configuration actually in force
    PUT  /api/config            update ingest defaults
    GET  /api/overview          one repo's headline numbers
    GET  /api/people            roster with knowledge mass
    GET  /api/timeline          every run + plan for a repo
    POST /api/ask               the eight-tool agent loop
    POST /api/drill             departure simulation
    POST /api/plan              handover plan from a drill
    POST /api/heal              apply a plan and re-measure
    GET  /api/findings          findings, latest drill by default
    GET  /api/memory            question log + counters
    GET  /api/graph             the console's map payload
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import db, memory, repos
from .agent import ask as agent_ask
from .config import settings
from .sim import engine, make_plan, metrics
from .sim.people import get_person, list_people
from .sim.plan import get_plan
from .tools.base import K, clean_ref, people_hint

app = FastAPI(title="BusFactor", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # local console; the API is read-only outside sims
    allow_methods=["*"],
    allow_headers=["*"],
)

_GRAPH_META = (
    "{nodeLabels:['Person','Module','Doc'], "
    "relationshipTypes:['KNOWS','OWNS','DOCUMENTS']}"
)


# ---------------------------------------------------------------------------
# request bodies
# ---------------------------------------------------------------------------


class AskBody(BaseModel):
    question: str
    repo: str = "main"


class DrillBody(BaseModel):
    person: str
    label: str | None = None
    repo: str = "main"


class PlanBody(BaseModel):
    sim_id: str | None = None
    include_resilience: bool = True
    repo: str = "main"


class HealBody(BaseModel):
    plan_id: str | None = None
    repo: str = "main"


class ConnectBody(BaseModel):
    source: str
    window_days: int | None = None


class ConfigBody(BaseModel):
    window_days: int | None = None


class ActionsBody(BaseModel):
    plan_id: str | None = None
    repo: str = "main"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _graph(repo: str | None) -> str:
    """`repo` is a registry slug; the graph name is a registry concern."""
    return repos.graph_for((repo or "main").strip() or "main")


def _count(graph: str, query: str) -> int:
    try:
        return int(db.ro(graph, query).result_set[0][0] or 0)
    except Exception:
        return 0


def _repo_worlds(graph: str) -> list[str]:
    rows = db.ro(graph, "MATCH (s:Sim) RETURN DISTINCT s.world").result_set
    return [graph, *sorted(w for (w,) in rows if w)]


# ---------------------------------------------------------------------------
# server + registry
# ---------------------------------------------------------------------------


@app.get("/api/health")
def health(repo: str = "main") -> dict:
    graph = _graph(repo)
    return {
        "ok": db.ping(),
        "repo": graph,
        "graphs": db.list_graphs(),
        "nodes": _count(graph, "MATCH (n) RETURN count(n)"),
        "edges": _count(graph, "MATCH ()-[r]->() RETURN count(r)"),
        "llm": settings.llm_enabled,
    }


@app.get("/api/repos")
def repos_list() -> dict:
    return {"repos": repos.list_repos(), "settings": repos.get_settings()}


@app.post("/api/repos")
def repos_connect(body: ConnectBody) -> dict:
    try:
        return repos.connect(body.source, body.window_days)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(400, str(e)) from e


@app.get("/api/config")
def config_get() -> dict:
    """What is actually in force — env defaults merged with what the user set."""
    ingest = repos.get_settings()
    return {
        "ingest": ingest,
        "coverage_floor": K,
        "llm_router": settings.llm_enabled,
        "github_token": bool(os.getenv("GITHUB_TOKEN")),
        "actions_repo": os.getenv("ACTIONS_REPO", "") or None,
    }


@app.put("/api/config")
def config_put(body: ConfigBody) -> dict:
    values = {}
    if body.window_days is not None:
        if not 30 <= body.window_days <= 3650:
            raise HTTPException(400, "window_days must be between 30 and 3650")
        values["window_days"] = body.window_days
    if values:
        repos.update_settings(values)
    return config_get()


# ---------------------------------------------------------------------------
# repo-scoped reads
# ---------------------------------------------------------------------------


@app.get("/api/overview")
def overview(repo: str = "main") -> dict:
    graph = _graph(repo)
    snap = metrics.snapshot(graph)
    return {
        "repo": graph,
        "summary": metrics.summary(snap),
        "coverage": snap["coverage"],
        "memory": {"stats": memory.stats(graph), "recent": memory.recent(graph, 6)},
        "worlds": _repo_worlds(graph),
    }


@app.get("/api/people")
def people(repo: str = "main") -> list[dict]:
    return list_people(_graph(repo))


@app.get("/api/timeline")
def timeline(repo: str = "main") -> dict:
    graph = _graph(repo)
    sims = db.ro(
        graph,
        "MATCH (s:Sim) RETURN s.id, s.kind, s.label, s.target_person, s.world, "
        "s.created_at, s.metrics_json, s.delta_json ORDER BY s.created_at",
    ).result_set
    plans = db.ro(
        graph,
        "MATCH (pl:Plan) OPTIONAL MATCH (pl)-[:HAS_STEP]->(st:Step) "
        "RETURN pl.id, pl.label, pl.status, pl.created_at, count(st) "
        "ORDER BY pl.created_at",
    ).result_set
    return {
        "repo": graph,
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
        "worlds": _repo_worlds(graph),
    }


@app.get("/api/findings")
def findings(repo: str = "main", sim_id: str | None = None) -> dict:
    graph = _graph(repo)
    if sim_id and sim_id != "latest":
        rows = db.ro(
            graph,
            "MATCH (s:Sim {id:$sid})-[:FOUND]->(f:Finding) "
            "RETURN s.id, f.id, f.kind, f.severity, f.claim, f.module_id, f.proof_json "
            "ORDER BY f.severity DESC, f.kind, f.module_id",
            {"sid": sim_id},
        ).result_set
    else:
        rows = db.ro(
            graph,
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


@app.get("/api/memory")
def mem(repo: str = "main") -> dict:
    graph = _graph(repo)
    return {"stats": memory.stats(graph), "recent": memory.recent(graph, 30)}


# ---------------------------------------------------------------------------
# actions
# ---------------------------------------------------------------------------


@app.post("/api/ask")
def ask(body: AskBody) -> dict:
    if not body.question.strip():
        raise HTTPException(400, "empty question")
    return agent_ask(body.question, _graph(body.repo))


@app.post("/api/drill")
def drill(body: DrillBody) -> dict:
    graph = _graph(body.repo)
    try:
        person = get_person(clean_ref(body.person), graph)
    except ValueError as e:
        raise HTTPException(404, f"{e}. {people_hint(graph)}") from e
    d = engine.run_drill(person["id"], body.label, graph)
    counts: dict[str, int] = {}
    for f in d["findings"]:
        counts[f["kind"]] = counts.get(f["kind"], 0) + 1
    return {**d, "counts": counts}


@app.post("/api/plan")
def plan(body: PlanBody) -> dict:
    try:
        return make_plan(body.sim_id, body.include_resilience, _graph(body.repo))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/heal")
def heal(body: HealBody) -> dict:
    try:
        return engine.run_heal(body.plan_id, _graph(body.repo))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/actions")
def actions(body: ActionsBody) -> dict:
    """Render the exact payload a live run would send.

    Preview only (I8): live mode needs an operator-owned target repo and a
    scoped token, both of which come from the environment, not the request.
    """
    graph = _graph(body.repo)
    try:
        plan = get_plan(graph, body.plan_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    person = get_person(plan["target_person"], graph)
    steps = plan["steps"]
    critical = ("sole_knower_lost", "module_blind")
    coverage = metrics.snapshot(graph)["coverage"]
    names = {p["id"]: p["name"] for p in list_people(graph)}

    def module_name(mid: str) -> str:
        return (coverage.get(mid) or {}).get("name", mid.removeprefix("m:"))

    payload = {
        "kind": "handover tracking issue",
        "title": f"Handover plan {plan['id']}: {person['name']} → team",
        "labels": ["knowledge-risk", "handover"],
        "body_markdown": "\n".join(
            [
                f"**Knowledge-risk handover** — {len(steps)} steps, planned from a measured drill.",
                "",
                *[
                    f"- [ ] `{module_name(s['module_id'])}` → "
                    f"**{names.get(s['teacher_id'], s['teacher_id'])}** — {s['note']}"
                    for s in steps
                ],
                "",
                "_Done when the healed world shows 0 stranded components._",
            ]
        ),
        "counts": {
            "steps": len(steps),
            "critical": sum(1 for s in steps if s["kind"] in critical),
            "thin": sum(1 for s in steps if s["kind"] == "coverage_thin"),
            "resilience": sum(1 for s in steps if s["kind"] == "resilience"),
        },
    }
    return {
        "mode": "preview",
        "plan_id": plan["id"],
        "target_repo": settings.actions_repo or None,
        "live_available": bool(settings.actions_repo and settings.github_token),
        "payload": payload,
    }


# ---------------------------------------------------------------------------
# console map
# ---------------------------------------------------------------------------


@app.get("/api/graph")
def graph(world: str = "main", repo: str = "main") -> dict:
    w = world or "main"
    graph_name = _graph(repo)
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
            "plan": source2 == "plan",
        }
        for src, typ, dst, w2, source2 in lrows
    ]

    cres = db.ro(
        w, f"CALL algo.WCC({_GRAPH_META}) YIELD node, componentId RETURN node.id, componentId"
    ).result_set
    comp = {nid: int(cid) for nid, cid in cres}

    sim_meta = None
    frows = db.ro(
        graph_name,
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
        "repo": graph_name,
        "nodes": nodes,
        "links": links,
        "sim": sim_meta,
        "findings": finding_list,
        "counts": {"nodes": len(nodes), "links": len(links)},
    }


_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"
if _DIST.exists():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="web")
