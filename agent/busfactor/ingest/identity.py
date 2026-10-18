"""Identity hygiene — collapse people records that are the same human.

A tokenless long-window pull surfaces one person under several author strings
("joegallo" next to "Joe Gallo", "colleen-j-mcginnis" next to "Colleen
McGinnis"). Snapshots key people by slugged author string, so such pairs
survive as two Person nodes with an identical display name — which makes name
lookups ambiguous ("I don't know X" while X is listed twice).

`collapse_same_name_people` folds people whose display names match
(case/space/punctuation-insensitive) into the most active record, rewrites
every person reference in the payload, and dedupes the edges the merge
collided.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime


def _norm(name: str) -> str:
    # case/space/punctuation-insensitive: "DvirDukhan" and "Dvir Dukhan" are
    # one human; so are "joegallo" and "Joe Gallo".
    return re.sub(r"[^a-z0-9]+", "", (name or "").casefold())


def _activity(p: dict) -> int:
    return (
        int(p.get("commits") or 0) * 2
        + int(p.get("reviews") or 0) * 3
        + int(p.get("prs") or 0)
    )


def _sort_key(iso: str) -> datetime:
    iso = (iso or "").replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(iso)
    except ValueError:
        return datetime.min


def _merge_iso(a: str, b: str, *, latest: bool) -> str:
    if not (a or b):
        return ""
    pick = max if latest else min
    return pick((a, b), key=_sort_key)


def collapse_same_name_people(
    body: dict, log: Callable[[str], None] = print
) -> dict[str, str]:
    """Merge same-display-name people in a snapshot payload (in place).

    Returns the {loser_id: winner_id} remap, already applied to the payload.
    """
    people: list[dict] = body.get("people") or []
    groups: dict[str, list[dict]] = {}
    for p in people:
        groups.setdefault(_norm(p.get("name") or ""), []).append(p)

    remap: dict[str, str] = {}
    drop: set[str] = set()
    for rows in groups.values():
        if len(rows) < 2:
            continue
        rows.sort(key=lambda p: (-_activity(p), str(p.get("id"))))
        win, losers = rows[0], rows[1:]
        for lose in losers:
            remap[lose["id"]] = win["id"]
            drop.add(lose["id"])
            for field in ("commits", "reviews", "prs"):
                win[field] = int(win.get(field) or 0) + int(lose.get(field) or 0)
            win["first_seen"] = _merge_iso(
                win.get("first_seen") or "", lose.get("first_seen") or "", latest=False
            )
            win["last_seen"] = _merge_iso(
                win.get("last_seen") or "", lose.get("last_seen") or "", latest=True
            )
            win["handle"] = win.get("handle") or lose.get("handle") or ""
            log(f"  identity: {lose['id']} folded into {win['id']} ('{win['name']}')")
    if not remap:
        return remap

    body["people"] = [p for p in people if p["id"] not in drop]
    log(
        f"  identity: {len(remap)} duplicate record(s) collapsed"
        f" -> {len(body['people'])} people"
    )

    def R(pid: str) -> str:
        return remap.get(pid, pid)

    def rewrite(rows: list[dict], key_fields: tuple[str, ...]) -> list[dict]:
        seen: set[tuple] = set()
        out: list[dict] = []
        for r in rows:
            r["person"] = R(r["person"])
            key = tuple(r[f] for f in key_fields) + (r["person"],)
            if key in seen:
                continue
            seen.add(key)
            out.append(r)
        return out

    def merge_edges(
        rows: list[dict],
        sum_fields: tuple[str, ...] = (),
        max_fields: tuple[str, ...] = (),
    ) -> list[dict]:
        out: dict[tuple[str, str], dict] = {}
        order: list[tuple[str, str]] = []
        for r in rows:
            r["person"] = R(r["person"])
            k = (r["module"], r["person"])
            if k not in out:
                out[k] = r
                order.append(k)
                continue
            tgt = out[k]
            for f in sum_fields:
                tgt[f] = round(float(tgt.get(f) or 0) + float(r.get(f) or 0), 4)
            for f in max_fields:
                tgt[f] = _merge_iso(tgt.get(f) or "", r.get(f) or "", latest=True)
        return [out[k] for k in order]

    body["knows"] = merge_edges(
        body.get("knows") or [],
        sum_fields=("commits", "reviews", "weight"),
        max_fields=("last_at",),
    )
    body["owns"] = merge_edges(body.get("owns") or [], sum_fields=("share",))
    body["authored"] = rewrite(body.get("authored") or [], ("pr",))
    body["wrote"] = rewrite(body.get("wrote") or [], ("doc",))
    body["decided_by"] = rewrite(body.get("decided_by") or [], ("decision",))
    body["reviewed"] = [
        {**r, "person": R(r["person"])} for r in body.get("reviewed") or []
    ]

    for doc in body.get("docs") or []:
        seen: list[str] = []
        for a in doc.get("authors") or []:
            a = R(a)
            if a not in seen:
                seen.append(a)
        doc["authors"] = seen

    return remap
