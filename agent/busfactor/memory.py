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
    tool: str | None,
) -> str:
    """Append a Question node + CITED edges. Best-effort, never breaks `ask`."""
    qid = f"q-{secrets.token_hex(3)}"
    try:
        db.rw(
            repo,
            "CREATE (q:Question {id:$id, text:$text, answer:$answer, "
            "outcome:$outcome, tool:$tool, created_at:$now})",
            {
                "id": qid,
                "text": text,
                "answer": answer,
                "outcome": outcome,
                "tool": tool or "",
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
        "q.created_at ORDER BY q.created_at DESC LIMIT $limit",
        {"limit": limit},
    ).result_set
    return [
        {
            "id": qid,
            "text": text,
            "answer": answer,
            "outcome": outcome,
            "tool": tool,
            "created_at": at,
        }
        for qid, text, answer, outcome, tool, at in rows
    ]


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
        "questions": c("MATCH (q:Question) RETURN count(q)"),
        "findings": c("MATCH (f:Finding) RETURN count(f)"),
        "runs": c("MATCH (s:Sim) RETURN count(s)"),
    }


def match_question(repo: str, text: str, threshold: float = 0.75) -> dict | None:
    """A repeat question deserves the earlier answer — that's memory working.

    Token overlap, at least two meaningful tokens, most recent prior hit wins.
    """
    toks = set(_tokens(text))
    if len(toks) < 2:
        return None
    for q in recent(repo, 50):
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
    tokens = _tokens(question)
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

    hits.sort(key=lambda h: (-h["score"], h["kind"], h["id"]))
    return hits[:limit]
