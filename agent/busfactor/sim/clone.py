"""World lifecycle: clone, prune.

Worlds are cheap — GRAPH.COPY on this graph takes milliseconds — so every
experiment gets its own. `main` is never mutated by an experiment.
"""

from __future__ import annotations

import secrets

from .. import db

MAX_WORLDS = 32


def new_world_id(kind: str) -> str:
    """`sim:drill-7f3a` style ids — kind-prefixed, unguessable enough to avoid collisions."""
    return f"sim:{kind}-{secrets.token_hex(2)}"


def clone_world(src: str, dest: str) -> None:
    db.graph(src).copy(dest)


def delete_world(world: str) -> None:
    try:
        db.client().select_graph(world).delete()
    except Exception:
        pass


def prune_worlds(keep: int = MAX_WORLDS) -> list[str]:
    """Delete the oldest world graphs beyond `keep`. Sim audit nodes stay in main."""
    try:
        rows = db.graph().ro_query(
            "MATCH (s:Sim) RETURN s.world, s.created_at ORDER BY s.created_at DESC"
        ).result_set
    except Exception:
        return []
    doomed = [w for (w, _t) in rows[keep:] if w]
    for w in doomed:
        delete_world(w)
    return doomed
