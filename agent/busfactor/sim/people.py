"""Person lookup against one repo graph: id exact, then best name match."""

from __future__ import annotations

from .. import db


def list_people(repo: str = "main") -> list[dict]:
    rows = db.ro(repo, 
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


def get_person(person_ref: str, repo: str = "main") -> dict:
    people = list_people(repo)
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
    if not hits:
        raise ValueError(f"unknown person '{person_ref}'")
    exact = [p for p in hits if (p["name"] or "").lower() == q]
    pool = exact or hits
    pool.sort(key=lambda p: (-p["commits"], -p["reviews"], p["id"]))
    return pool[0]
