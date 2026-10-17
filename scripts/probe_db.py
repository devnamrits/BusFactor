"""Diagnostic: verify the FalkorDB client surface + algorithm syntax on this server.

Run:  cd agent && uv run python ../scripts/probe_db.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from busfactor import db  # noqa: E402


def show(step: str, fn):
    try:
        out = fn()
        print(f"OK   {step}: {out}")
        return out
    except Exception as e:  # noqa: BLE001 — probe wants to report everything
        print(f"FAIL {step}: {type(e).__name__}: {e}")
        return None


def main() -> None:
    c = db.client()
    print("client:", type(c).__name__)
    show("list_graphs", lambda: c.list_graphs()[:10])

    for name in ("probe", "probe_copy"):
        try:
            c.select_graph(name).delete()
        except Exception:
            pass

    g = c.select_graph("probe")
    show(
        "seed",
        lambda: g.query(
            "CREATE (a:Person {id:'p:a', name:'Ada', status:'active'}) "
            ", (b:Person {id:'p:b', name:'Bo', status:'active'}) "
            ", (m:Module {id:'m:x', name:'core'}) "
            ", (d:Doc {id:'d:r', path:'README.md'}) "
            "CREATE (a)-[:KNOWS {weight:0.9, cost:0.1}]->(m) "
            ", (b)-[:KNOWS {weight:0.4, cost:0.6}]->(m) "
            ", (a)-[:OWNS {source:'test'}]->(m) "
            ", (b)-[:WROTE]->(d)"
        ).result_set,
    )
    show("count", lambda: g.ro_query("MATCH (n) RETURN count(n)").result_set)
    show(
        "wcc",
        lambda: g.ro_query(
            "CALL algo.WCC({nodeLabels:['Person','Module','Doc'], "
            "relationshipTypes:['KNOWS','OWNS']}) YIELD node, componentId "
            "RETURN count(DISTINCT componentId)"
        ).result_set,
    )
    show(
        "pagerank-positional",
        lambda: g.ro_query(
            "CALL algo.pageRank('Module','KNOWS') YIELD node, score RETURN score"
        ).result_set,
    )
    show(
        "betweenness",
        lambda: g.ro_query(
            "CALL algo.betweenness({nodeLabels:['Person'], relationshipTypes:['KNOWS'], "
            "samplingSize:10, samplingSeed:42}) YIELD node, betweenness "
            "RETURN node.name, betweenness ORDER BY betweenness DESC"
        ).result_set,
    )
    show(
        "sppaths",
        lambda: g.ro_query(
            "MATCH (a:Person {id:'p:b'}), (m:Module {id:'m:x'}) "
            "CALL algo.SPpaths({sourceNode:a, targetNode:m, relTypes:['KNOWS'], "
            "weightProp:'cost', relDirection:'incoming', pathCount:3, maxLen:4}) "
            "YIELD path RETURN path"
        ).result_set,
    )
    show("add-ep", lambda: g.query("MATCH (p:Person {id:'p:b'}) SET p.status='departed'").result_set)
    show("copy", lambda: g.copy("probe_copy"))
    show("list-after-copy", lambda: c.list_graphs())
    gc = c.select_graph("probe_copy")
    show("copy-visible", lambda: gc.ro_query("MATCH (n) RETURN count(n)").result_set)
    show("copy-isolation", lambda: gc.ro_query("MATCH (p:Person) RETURN p.name, p.status ORDER BY p.name").result_set)
    show("index-new-syntax", lambda: g.query("CREATE INDEX FOR (p:Person) ON (p.name)"))
    show("indexes", lambda: g.query("CALL db.indexes()").result_set)
    show("ro-write-refused", lambda: g.ro_query("CREATE (n:Evil)").result_set)

    for name in ("probe", "probe_copy"):
        show(f"delete-{name}", lambda name=name: c.select_graph(name).delete())


if __name__ == "__main__":
    main()
