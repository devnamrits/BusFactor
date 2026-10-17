"""Load a pinned snapshot into FalkorDB — batched, verified, deterministic."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable, Iterator

from .. import db

BATCH = 500

NODE_PROPS: dict[str, list[str]] = {
    "Person": ["id", "name", "handle", "status", "first_seen", "last_seen",
               "commits", "reviews", "prs"],
    "Module": ["id", "name", "path", "commits_window", "first_seen", "last_seen",
               "criticality"],
    "Doc": ["id", "path", "title", "kind", "authors"],
    "Decision": ["id", "title", "status", "decided_at", "source", "source_ref"],
    "PR": ["id", "number", "title", "merged_at", "author_login", "url"],
}

# type -> (src label, src row field, dst label, dst row field, prop names)
EDGE_SPECS: dict[str, tuple[str, str, str, str, list[str]]] = {
    "KNOWS": ("Person", "person", "Module", "module",
              ["weight", "cost", "source", "commits", "reviews", "last_at"]),
    "OWNS": ("Person", "person", "Module", "module", ["source", "share"]),
    "AUTHORED": ("Person", "person", "PR", "pr", []),
    "REVIEWED": ("Person", "person", "PR", "pr", ["reviews", "last_at"]),
    "TOUCHES": ("PR", "pr", "Module", "module", []),
    "WROTE": ("Person", "person", "Doc", "doc", []),
    "DECIDED_BY": ("Decision", "decision", "Person", "person", []),
    "AFFECTS": ("Decision", "decision", "Module", "module", []),
}

INDEXES = [
    # FalkorDB index syntax, with a legacy fallback applied in code.
    "CREATE INDEX FOR (p:Person) ON (p.id)",
    "CREATE INDEX FOR (p:Person) ON (p.name)",
    "CREATE INDEX FOR (m:Module) ON (m.id)",
    "CREATE INDEX FOR (m:Module) ON (m.name)",
    "CREATE INDEX FOR (d:Doc) ON (d.path)",
    "CREATE INDEX FOR (s:Sim) ON (s.id)",
    "CREATE INDEX FOR (q:Question) ON (q.id)",
    "CREATE INDEX FOR (f:Finding) ON (f.id)",
    "CREATE INDEX FOR (pl:Plan) ON (pl.id)",
    "CREATE INDEX FOR (st:Step) ON (st.id)",
]

LEGACY_INDEXES = [
    "CREATE INDEX ON :Person(id)",
    "CREATE INDEX ON :Person(name)",
    "CREATE INDEX ON :Module(id)",
    "CREATE INDEX ON :Module(name)",
    "CREATE INDEX ON :Doc(path)",
    "CREATE INDEX ON :Sim(id)",
    "CREATE INDEX ON :Question(id)",
    "CREATE INDEX ON :Finding(id)",
    "CREATE INDEX ON :Plan(id)",
    "CREATE INDEX ON :Step(id)",
]

LABELS = ("Person", "Module", "Doc", "Decision", "PR", "Sim", "Finding", "Plan",
          "Step", "Question")


def verify_sha(body: dict) -> str:
    """Recompute the canonical hash and compare with meta.snapshot_sha256."""
    want = (body.get("meta") or {}).get("snapshot_sha256")
    copy = json.loads(json.dumps(body))
    (copy.get("meta") or {}).pop("snapshot_sha256", None)
    canon = json.dumps(copy, sort_keys=True, separators=(",", ":"))
    got = hashlib.sha256(canon.encode()).hexdigest()
    if want and want != got:
        raise RuntimeError(f"snapshot hash mismatch: computed {got[:12]}, meta says {want[:12]}")
    return got


def _chunks(rows: list, size: int = BATCH) -> Iterator[list]:
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def _count(g, query: str) -> int:
    # FalkorDB refuses reads on a graph key that does not exist yet.
    try:
        rows = g.ro_query(query).result_set
    except Exception:
        return 0
    return int(rows[0][0]) if rows else 0


def _load_nodes(g, label: str, objs: Iterable[dict], log=print) -> int:
    props = NODE_PROPS[label]
    sets = ", ".join(f"n.{p} = r.{p}" for p in props)
    query = f"UNWIND $rows AS r CREATE (n:{label}) SET {sets}"
    total = 0
    rows = [{p: o.get(p) for p in props} for o in objs]
    for chunk in _chunks(rows):
        g.query(query, {"rows": chunk})
        total += len(chunk)
    log(f"  {label:<9} {total}")
    return total


def _load_edges(g, etype: str, objs: list[dict], log=print) -> int:
    src_label, src_field, dst_label, dst_field, props = EDGE_SPECS[etype]
    sets = (" SET " + ", ".join(f"e.{p} = r.{p}" for p in props)) if props else ""
    query = (
        f"UNWIND $rows AS r "
        f"MATCH (a:{src_label} {{id: r.{src_field}}}), (b:{dst_label} {{id: r.{dst_field}}}) "
        f"CREATE (a)-[e:{etype}]->(b){sets}"
    )
    rows = []
    for o in objs:
        row = {src_field: o[src_field], dst_field: o[dst_field]}
        for p in props:
            row[p] = o.get(p)
        rows.append(row)
    total = 0
    for chunk in _chunks(rows):
        g.query(query, {"rows": chunk})
        total += len(chunk)
    log(f"  {etype:<9} {total}")
    return total


def _create_indexes(g, log=print) -> None:
    created = 0
    for stmt, legacy in zip(INDEXES, LEGACY_INDEXES):
        try:
            g.query(stmt)
            created += 1
        except Exception:
            try:
                g.query(legacy)
                created += 1
            except Exception as e:  # pragma: no cover — server-version dependent
                log(f"  index skipped ({stmt}): {e}")
    log(f"  indexes  {created}/{len(INDEXES)}")


def _compute_criticality(g, log=print) -> None:
    """Cache each module's knowledge mass (sum of KNOWS weights) on the node.

    algo.pageRank degenerates to a uniform score on the bipartite
    Person -> Module knowledge view (verified empirically against this
    server), so the honest criticality measure is the weighted in-degree
    rollup — every module's total depended-upon knowledge.
    """
    try:
        res = g.ro_query(
            "MATCH (m:Module)<-[k:KNOWS]-(:Person) RETURN m.id, sum(k.weight)"
        ).result_set
        rows = [{"id": r[0], "mass": round(float(r[1] or 0.0), 6)} for r in res if r[0]]
        if rows:
            g.query(
                "UNWIND $rows AS r MATCH (m:Module {id: r.id}) SET m.criticality = r.mass",
                {"rows": rows},
            )
        log(f"  criticality {len(rows)} modules (knowledge mass)")
    except Exception as e:
        log(f"  criticality skipped: {e}")


def graph_stats(g) -> dict:
    stats: dict = {"nodes": {}, "edges": {}, "total_nodes": 0, "total_edges": 0}
    for label in LABELS:
        n = _count(g, f"MATCH (n:{label}) RETURN count(n)")
        if n:
            stats["nodes"][label] = n
    stats["total_nodes"] = sum(stats["nodes"].values())
    try:
        res = g.ro_query("MATCH ()-[e]->() RETURN type(e) AS t, count(e) AS n").result_set
        for t, n in res:
            stats["edges"][t] = int(n)
    except Exception:
        pass
    stats["total_edges"] = sum(stats["edges"].values())
    return stats


def load_snapshot(
    path: Path,
    *,
    graph_name: str = "main",
    force: bool = False,
    log=print,
) -> dict:
    body = json.loads(Path(path).read_text())
    sha = verify_sha(body)
    meta = body.get("meta") or {}
    log(f"snapshot {Path(path).name}: {meta.get('repo_url')} @ {str(meta.get('head_commit'))[:10]} sha {sha[:12]}")

    g = db.graph(graph_name)
    existing = _count(g, "MATCH (n) RETURN count(n)")
    if existing and not force:
        raise RuntimeError(
            f"graph '{graph_name}' already has {existing} nodes — pass --force to rebuild"
        )
    if existing:
        log(f"replacing '{graph_name}' ({existing} nodes)")
        g.delete()
        g = db.graph(graph_name)

    log("nodes:")
    _load_nodes(g, "Person", body["people"], log)
    _load_nodes(g, "Module", body["modules"], log)
    _load_nodes(g, "Doc", body["docs"], log)
    _load_nodes(g, "Decision", body["decisions"], log)
    _load_nodes(g, "PR", body["prs"], log)

    knows = [dict(r, cost=round(1.0 - float(r["weight"]), 4)) for r in body["knows"]]
    log("edges:")
    _load_edges(g, "KNOWS", knows, log)
    _load_edges(g, "OWNS", body["owns"], log)
    _load_edges(g, "AUTHORED", body["authored"], log)
    _load_edges(g, "REVIEWED", body["reviewed"], log)
    _load_edges(g, "TOUCHES", body["touches"], log)
    _load_edges(g, "WROTE", body["wrote"], log)
    _load_edges(g, "DECIDED_BY", body["decided_by"], log)
    _load_edges(g, "AFFECTS", body["affects"], log)

    log("post:")
    _create_indexes(g, log)
    _compute_criticality(g, log)

    stats = graph_stats(g)
    log(f"  graph '{graph_name}': {stats['total_nodes']} nodes · {stats['total_edges']} edges")
    return stats
