"""FalkorDB access layer — the only module that talks to the database.

Reads go through `ro_query` (invariant I6). Writes are reserved for the loader
and for sim worlds; the agent loop never writes to `main` outside audit nodes.
"""

from __future__ import annotations

from typing import Any

from falkordb import FalkorDB
from redis.exceptions import ResponseError

from .config import settings

_MISSING_GRAPH_ERR = "Invalid graph operation on empty key"

_client: FalkorDB | None = None


def _is_missing_graph(err: Exception) -> bool:
    """True when FalkorDB refused a read because the graph was never created."""
    return _MISSING_GRAPH_ERR in str(err)


class _EmptyResult:
    """'No rows' for a graph that does not exist yet (repo still indexing).

    Every read path treats this exactly like an empty result set, so a
    building repo shows empty panels instead of an HTTP 500.
    """

    def __init__(self) -> None:
        self.result_set: list = []
        self.header: list = []


def client() -> FalkorDB:
    """Lazy singleton connection."""
    global _client
    if _client is None:
        kwargs: dict[str, Any] = {
            "host": settings.falkordb_host,
            "port": settings.falkordb_port,
        }
        if settings.falkordb_username:
            kwargs["username"] = settings.falkordb_username
        if settings.falkordb_password:
            kwargs["password"] = settings.falkordb_password
        _client = FalkorDB(**kwargs)
    return _client


def graph(name: str | None = None):
    """Select a graph — `main` by default."""
    return client().select_graph(name or settings.main_graph)


def ro(name: str, query: str, params: dict | None = None):
    """Read-only query (invariant I6): cannot mutate, cheapest path."""
    try:
        return graph(name).ro_query(query, params or {})
    except ResponseError as e:
        if _is_missing_graph(e):
            return _EmptyResult()
        raise


def rw(name: str, query: str, params: dict | None = None):
    """Read-write query — loader and sim worlds only."""
    return graph(name).query(query, params or {})


def list_graphs() -> list[str]:
    try:
        return sorted(client().list_graphs())
    except Exception:
        return []


def sim_worlds() -> list[str]:
    return [g for g in list_graphs() if g.startswith("sim:")]


def ping() -> bool:
    """True when the server answers — independent of whether any graph exists."""
    try:
        client().list_graphs()
        return True
    except Exception:
        return False
