"""Every number a drill reports, as plain Cypher over one world.

The same queries run against `main` and against sim worlds with no
special-casing: a departed person disappears from coverage because their
world no longer holds their knowledge edges — not because a query checks
for a status flag.
"""

from __future__ import annotations

from .. import db

_GK = "{nodeLabels:['Person','Module','Doc'], relationshipTypes:['KNOWS','OWNS','DOCUMENTS']}"


def _rows(world: str, query: str, params: dict | None = None) -> list:
    return db.ro(world, query, params).result_set


def coverage(world: str) -> dict[str, dict]:
    """module_id -> {name, commits, knowers: [{id, name}]} (active people only)."""
    mods = _rows(world, "MATCH (m:Module) RETURN m.id, m.name, m.commits_window")
    out: dict[str, dict] = {
        mid: {"name": nm, "commits": int(c or 0), "knowers": []} for mid, nm, c in mods
    }
    for mid, pid, pname in _rows(
        world,
        "MATCH (p:Person {status:'active'})-[:KNOWS|OWNS]->(m:Module) "
        "RETURN m.id, p.id, p.name",
    ):
        if mid in out:
            out[mid]["knowers"].append({"id": pid, "name": pname})
    for info in out.values():
        info["knowers"].sort(key=lambda k: k["id"])
    return out


def islands(world: str) -> list[dict]:
    """Components of G_k with >=1 Module and no active Person — stranded knowledge."""
    rows = _rows(
        world,
        f"CALL algo.WCC({_GK}) YIELD node, componentId "
        "RETURN componentId, labels(node), node.status, "
        "coalesce(node.name, node.title, node.path)",
    )
    comps: dict[object, dict] = {}
    for cid, labels, status, name in rows:
        c = comps.setdefault(
            cid, {"id": cid, "has_module": False, "has_active": False, "members": []}
        )
        labels = labels or []
        if "Module" in labels:
            c["has_module"] = True
        if "Person" in labels and status == "active":
            c["has_active"] = True
        if name:
            c["members"].append(name)
    out = [c for c in comps.values() if c["has_module"] and not c["has_active"]]
    for c in out:
        c["members"].sort()
    out.sort(key=lambda c: c["members"])
    return out


def active_person_components(world: str) -> int:
    """How many separate groups of people the knowledge graph holds."""
    rows = _rows(
        world,
        f"CALL algo.WCC({_GK}) YIELD node, componentId "
        "RETURN componentId, labels(node), node.status",
    )
    comps: dict[object, bool] = {}
    for cid, labels, status in rows:
        comps.setdefault(cid, False)
        if "Person" in (labels or []) and status == "active":
            comps[cid] = True
    return sum(1 for v in comps.values() if v)


def decisions(world: str) -> list[dict]:
    base = _rows(world, "MATCH (d:Decision) RETURN d.id, d.title, d.decided_at")
    out: dict[str, dict] = {
        did: {"id": did, "title": title, "decided_at": at, "deciders": [], "active": []}
        for did, title, at in base
    }
    for did, pid, pname, status in _rows(
        world,
        "MATCH (d:Decision)-[:DECIDED_BY]->(p:Person) "
        "RETURN d.id, p.id, p.name, p.status",
    ):
        d = out.get(did)
        if d is None:
            continue
        d["deciders"].append({"id": pid, "name": pname, "status": status})
        if status == "active":
            d["active"].append({"id": pid, "name": pname})
    for d in out.values():
        d["deciders"].sort(key=lambda x: x["id"])
        d["active"].sort(key=lambda x: x["id"])
    return [out[k] for k in sorted(out)]


def summary(snap: dict) -> dict:
    """Compact numbers for the timeline / filmstrip."""
    return {
        "modules": len(snap["coverage"]),
        "zero_modules": len(snap["zero_modules"]),
        "bus_factor": snap["bus_factor"],
        "islands": len(snap["islands"]),
        "orphaned_decisions": len(snap["decisions_orphaned"]),
        "person_components": snap["active_person_components"],
    }


def snapshot(world: str) -> dict:
    """The full measurable state of one world."""
    cov = coverage(world)
    isl = islands(world)
    dec = decisions(world)
    known = [len(c["knowers"]) for c in cov.values() if c["knowers"]]
    return {
        "world": world,
        "coverage": cov,
        "zero_modules": sorted(mid for mid, c in cov.items() if not c["knowers"]),
        "bus_factor": min(known) if known else 0,
        "islands": isl,
        "decisions": dec,
        "decisions_orphaned": sorted(
            d["id"] for d in dec if d["deciders"] and not d["active"]
        ),
        "active_person_components": active_person_components(world),
    }
