"""Memory is a first-class citizen: every question becomes a node.

Questions, answers and what they cited live in the repo graph next to the
facts (append-only, invariant I7). `recall` searches this store, so the
system gets more useful the longer a team uses it — and the memory itself
is queryable Cypher.
"""

from __future__ import annotations

import re
import secrets
from datetime import UTC, datetime

from . import db

# citation kind -> graph label (ids must match node `id` properties)
LABELS = {
    "person": "Person",
    "module": "Module",
    "doc": "Doc",
    "decision": "Decision",
    "pr": "PR",
    "sim": "Sim",
    "plan": "Plan",
    "finding": "Finding",
    "question": "Question",
}

STOP = {
    "who", "what", "when", "where", "why", "how", "the", "a", "an", "of", "in",
    "on", "for", "to", "is", "are", "was", "were", "did", "do", "does", "and",
    "or", "about", "with", "from", "can", "could", "should", "would", "will",
    "we", "our", "us", "it", "this", "that", "they", "them", "leave", "leaves",
    "left", "leaving", "knows", "known", "know", "team", "person", "people",
}


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _tokens(text: str) -> list[str]:
    return [
        t
        for t in re.findall(r"[a-z0-9][a-z0-9/_.\-]{1,}", (text or "").lower())
        if t not in STOP
    ]


# Memory answers are stored canonically, but earlier builds wrapped them on
# every repeat — so unwrap defensively: a memory of a memory must never leak.
_WRAPPED = re.compile(
    r"^From memory — I answered (?:this earlier|this before) \(q-[0-9a-f]+\): "
)


def canonical_answer(text: str) -> str:
    """Strip any nesting of the "From memory — …" framing to the real answer."""
    out = text or ""
    while True:
        stripped = _WRAPPED.sub("", out, count=1)
        if stripped == out:
            return out.strip()
        out = stripped


def record_question(
    repo: str, text: str, answer: str, outcome: str, citations: list[dict],
    tool: str | None, world: str = "",
) -> str:
    """Append a Question node + CITED edges. Best-effort, never breaks `ask`.

    `world` names the graph an answer was computed against when that was a
    drill/heal copy rather than the repo itself — it keeps world answers from
    replaying later as if they were snapshot answers.
    """
    qid = f"q-{secrets.token_hex(3)}"
    try:
        db.rw(
            repo,
            "CREATE (q:Question {id:$id, text:$text, answer:$answer, "
            "outcome:$outcome, tool:$tool, world:$world, created_at:$now})",
            {
                "id": qid,
                "text": text,
                "answer": answer,
                "outcome": outcome,
                "tool": tool or "",
                "world": world,
                "now": _now(),
            },
        )
        for kind, label in LABELS.items():
            if kind == "question":
                continue
            ids = [
                c["id"] for c in citations
                if c.get("kind") == kind and c.get("id")
            ]
            if not ids:
                continue
            db.rw(
                repo,
                f"MATCH (q:Question {{id:$qid}}) UNWIND $ids AS x "
                f"MATCH (n:{label} {{id:x}}) CREATE (q)-[:CITED]->(n)",
                {"qid": qid, "ids": list(dict.fromkeys(ids))},
            )
    except Exception as e:  # memory is an add-on; the answer still stands
        print(f"[memory] record failed: {e}")
    return qid


def recent(repo: str, limit: int = 12) -> list[dict]:
    rows = db.ro(
        repo,
        "MATCH (q:Question) RETURN q.id, q.text, q.answer, q.outcome, q.tool, "
        "coalesce(q.world, ''), q.created_at ORDER BY q.created_at DESC LIMIT $limit",
        {"limit": limit},
    ).result_set
    return [
        {
            "id": qid,
            "text": text,
            "answer": answer,
            "outcome": outcome,
            "tool": tool,
            "world": world,
            "created_at": at,
        }
        for qid, text, answer, outcome, tool, world, at in rows
    ]


def cited_nodes(repo: str, qid: str) -> list[dict]:
    """What an earlier answer pointed at, rebuilt as replayable citations.

    Replays used to cite only the old Question node, which the console cannot
    draw — so a remembered answer never lit up the map. The original answer's
    CITED edges carry the real graph ids; rebuild citations from them.
    """
    try:
        rows = db.ro(
            repo,
            "MATCH (q:Question {id:$qid})-[:CITED]->(n) "
            "RETURN labels(n)[0], n.id, coalesce(n.name, n.title, n.path, n.id)",
            {"qid": qid},
        ).result_set
    except Exception:
        return []
    kind_of = {
        (label or "").lower(): kind
        for kind, label in LABELS.items()
        if kind != "question"
    }
    out: list[dict] = []
    seen: set[str] = set()
    for lab, nid, name in rows:
        kind = kind_of.get((lab or "").lower())
        if not kind or nid in seen:
            continue
        seen.add(nid)
        out.append({"kind": kind, "id": nid, "label": name or nid})
    return out


def stats(repo: str) -> dict:
    def c(query: str) -> int:
        try:
            return int(db.ro(repo, query).result_set[0][0] or 0)
        except Exception:
            return 0

    return {
        "people": c("MATCH (p:Person) RETURN count(p)"),
        "modules": c("MATCH (m:Module) RETURN count(m)"),
        "decisions": c("MATCH (d:Decision) RETURN count(d)"),
        "docs": c("MATCH (d:Doc) RETURN count(d)"),
        "prs": c("MATCH (pr:PR) RETURN count(pr)"),
        "questions": c("MATCH (q:Question) RETURN count(q)"),
        "findings": c("MATCH (f:Finding) RETURN count(f)"),
        "runs": c("MATCH (s:Sim) RETURN count(s)"),
    }


def match_question(
    repo: str, text: str, threshold: float = 0.75, world: str = ""
) -> dict | None:
    """A repeat question deserves the earlier answer — that's memory working.

    Token overlap, at least two meaningful tokens, most recent prior hit wins.
    Only answers from the same world qualify — a drill/heal answer must never
    replay as a snapshot answer, or vice versa.
    """
    toks = set(_tokens(text))
    if len(toks) < 2:
        return None
    for q in recent(repo, 50):
        if (q.get("world") or "") != world:
            continue
        if q["tool"] == "recall":
            # an answer that was itself a memory lookup must not be recycled —
            # stale recall hints would otherwise shadow the real tools forever
            continue
        pt = set(_tokens(q["text"]))
        if not pt:
            continue
        overlap = len(toks & pt) / len(toks)
        if overlap >= threshold:
            return {**q, "overlap": round(overlap, 2)}
    return None


def search(repo: str, question: str, limit: int = 6) -> list[dict]:
    """Score every remembered surface by token overlap — no embeddings needed
    at team scale, and the result is explainable: here is the overlap."""
    tokens = [t for t in _tokens(question) if t not in ("pr", "prs", "repo", "repository")]
    if not tokens:
        return []
    hits: list[dict] = []

    # past questions (a previous answer is the strongest memory)
    for qid, text, answer, outcome, at in db.ro(
        repo,
        "MATCH (q:Question) RETURN q.id, q.text, q.answer, q.outcome, q.created_at "
        "ORDER BY q.created_at DESC LIMIT 100",
    ).result_set:
        score = sum(1 for t in tokens if t in (text or "").lower())
        if score:
            hits.append({
                "kind": "question", "id": qid, "label": text, "answer": answer,
                "snippet": text, "detail": at or "", "score": 1.5 * score,
            })

    # recorded decisions
    for did, title, at, ref in db.ro(
        repo,
        "MATCH (d:Decision) RETURN d.id, d.title, d.decided_at, d.source_ref",
    ).result_set:
        score = sum(1 for t in tokens if t in (title or "").lower())
        if score:
            deciders = [
                p for (p,) in db.ro(
                    repo,
                    "MATCH (d:Decision {id:$id})-[:DECIDED_BY]->(p:Person) RETURN p.name",
                    {"id": did},
                ).result_set
            ]
            hits.append({
                "kind": "decision", "id": did, "label": title or did,
                "detail": ref or "", "deciders": deciders,
                "score": 2.0 * score,
            })

    # previous runs
    for sid, label, kind, at in db.ro(
        repo,
        "MATCH (s:Sim) RETURN s.id, s.label, s.kind, s.created_at "
        "ORDER BY s.created_at DESC LIMIT 30",
    ).result_set:
        score = sum(1 for t in tokens if t in (label or "").lower())
        if score:
            hits.append({
                "kind": "sim", "id": sid, "label": label, "detail": f"{kind} · {at}",
                "score": 1.0 * score,
            })

    # findings from previous drills
    for fid, claim, fkind, mid in db.ro(
        repo,
        "MATCH (f:Finding) RETURN f.id, f.claim, f.kind, f.module_id LIMIT 300",
    ).result_set:
        score = sum(1 for t in tokens if t in (claim or "").lower())
        if score:
            hits.append({
                "kind": "finding", "id": fid, "label": claim, "detail": fkind,
                "score": 1.2 * score,
            })

    # people and modules named in the question
    for pid, name in db.ro(repo, "MATCH (p:Person) RETURN p.id, p.name").result_set:
        score = sum(1 for t in tokens if t in (name or "").lower())
        if score:
            hits.append({
                "kind": "person", "id": pid, "label": name,
                "score": 1.8 * score,
            })
    for mid2, name in db.ro(repo, "MATCH (m:Module) RETURN m.id, m.name").result_set:
        score = sum(1 for t in tokens if t in (name or "").lower())
        if score:
            hits.append({
                "kind": "module", "id": mid2, "label": name,
                "score": 1.8 * score,
            })

    # docs and merged PRs. Broad words ("docs", "prs") would flood every
    # search, so only content words of 4+ chars and PR numbers count here.
    stop = {
        "docs", "documentation", "prs", "pull", "requests", "merged",
        "pages", "page",
    }
    strong = [t for t in tokens if len(t) >= 4 and t not in stop]
    for did, title, path in db.ro(
        repo, "MATCH (d:Doc) RETURN d.id, d.title, d.path"
    ).result_set:
        score = sum(
            1 for t in strong if re.search(rf"\b{t}", (title or "").lower())
        )
        if score:
            hits.append({
                "kind": "doc", "id": did, "label": title or did,
                "detail": path or "", "score": 1.6 * score,
            })
    for pid2, num, title, at in db.ro(
        repo, "MATCH (pr:PR) RETURN pr.id, pr.number, pr.title, pr.merged_at"
    ).result_set:
        score = sum(
            1 for t in strong
            if t == str(num) or re.search(rf"\b{t}", (title or "").lower())
        )
        if score:
            hits.append({
                "kind": "pr", "id": pid2,
                "label": f"PR #{num} — {title}" if title else f"PR #{num}",
                "detail": at or "", "score": 1.2 * score,
            })

    hits.sort(key=lambda h: (-h["score"], h["kind"], h["id"]))
    return hits[:limit]
