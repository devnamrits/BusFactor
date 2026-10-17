"""Cypher lives in versioned files — every query the agent runs is readable.

The agent never writes Cypher at runtime (invariant I5): it picks a named
query from this folder, parameterised, and runs it read-only (I6).
"""

from __future__ import annotations

from pathlib import Path

from .. import db

_DIR = Path(__file__).resolve().parent / "queries"


def load(name: str) -> str:
    text = (_DIR / f"{name}.cypher").read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith("//")]
    return "\n".join(lines).strip()


def run(name: str, params: dict | None = None, world: str = "main") -> list:
    return db.ro(world, load(name), params or {}).result_set
