"""Person lookup against main: exact id first, then unambiguous name/handle."""

from __future__ import annotations

from .. import db


def list_people() -> list[dict]:
    rows = db.graph().ro_query(
        "MATCH (p:Person) RETURN p.id, p.name, p.handle, p.status, p.commits, "
        "p.reviews, p.last_seen ORDER BY p.commits DESC, p.id"
    ).result_set
    return [
        {
            "id": pid,
            "name": name,
            "handle": handle or "",
            "status": status or "active",
            "commits": int(commits or 0),
            "reviews": int(reviews or 0),
            "last_seen": last or "",
        }
        for pid, name, handle, status, commits, reviews, last in rows
    ]


def get_person(person_ref: str) -> dict:
    people = list_people()
    for p in people:
        if p["id"] == person_ref:
            return p
    q = (person_ref or "").strip().lower()
    if not q:
        raise ValueError("empty person reference")
    hits = [
        p
        for p in people
        if q in (p["name"] or "").lower() or q == (p["handle"] or "").lower()
    ]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise ValueError(
            f"ambiguous person '{person_ref}': {', '.join(p['name'] for p in hits)}"
        )
    raise ValueError(f"unknown person '{person_ref}'")
