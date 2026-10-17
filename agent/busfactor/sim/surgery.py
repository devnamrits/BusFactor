"""Removing a person from a world — the only mutation a drill performs.

The person stays as a ghost (`status = 'departed'`); their KNOWS/OWNS
knowledge edges go. Artifact edges (AUTHORED, WROTE, DECIDED_BY, ...) stay —
history happened; the knowledge left with them.
"""

from __future__ import annotations

from .. import db

_MARK = "MATCH (p:Person {id: $pid}) SET p.status = 'departed'"
_DROP = "MATCH (p:Person {id: $pid})-[k:KNOWS|OWNS]->() DELETE k"


def remove_person(world: str, person_id: str) -> None:
    db.rw(world, _MARK, {"pid": person_id})
    db.rw(world, _DROP, {"pid": person_id})
