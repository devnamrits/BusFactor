"""ask() — one question in, one cited answer out, memory appended.

The loop is deliberately thin: route → run one tool → validate numbers →
record the question. All the intelligence lives in the tools and the graph.
"""

from __future__ import annotations

import time

from . import memory, planner, validator
from .tools import TOOLS


def ask(question: str, repo: str = "main", memory_repo: str | None = None) -> dict:
    """`repo` is the graph the question runs against (it may be a drill/heal
    world); `memory_repo` defaults to it and is where the turn is remembered."""
    t0 = time.time()
    question = (question or "").strip()
    mem = memory_repo or repo
    world_tag = "" if repo == mem else repo
    if not question:
        return {
            "question": question,
            "answer": "Ask me something about the team's knowledge — e.g. 'who "
                      "can we least afford to lose?'",
            "outcome": "bad_input",
            "tool": None,
            "ok": False,
            "data": {},
            "citations": [],
            "routing": None,
            "validated": True,
            "issues": [],
            "question_id": None,
            "seconds": 0.0,
        }

    # Memory first: if we answered this before, reuse it — that's the point
    # of remembering. Anything else routes fresh.
    prior = memory.match_question(repo, question, world=world_tag)
    if prior:
        routing = {
            "tool": "recall",
            "args": {},
            "engine": "memory",
            "reason": (
                f"repeat question (token overlap {prior['overlap']}) — "
                f"answering from memory of {prior['id']}"
            ),
        }
        canonical = memory.canonical_answer(prior["answer"])
        # cite what the original answer cited (not the wrapper question) —
        # otherwise the map has nothing to light up when a memory replays
        cites = memory.cited_nodes(mem, prior["id"])
        if not cites:
            cites = [{
                "kind": "question",
                "id": prior["id"],
                "label": "earlier question",
                "detail": prior["text"],
            }]
        res = {
            "tool": "recall",
            "ok": True,
            "outcome": "answered_from_memory",
            "answer": f"From memory — I answered this earlier ({prior['id']}): {canonical}",
            "data": {"prior": prior},
            "citations": cites,
        }
        v = validator.validate(res)
        # Record the factual answer, not the framing — otherwise every repeat
        # nests one more "From memory" layer around the previous answer.
        qid = memory.record_question(
            mem, question, canonical, res["outcome"], res["citations"], "recall",
            world=world_tag,
        )
        return _envelope(question, res, routing, v, qid, t0)

    routing = planner.plan(question)
    tool = routing["tool"]
    args = dict(routing.get("args") or {})
    args.pop("repo", None)
    try:
        res = TOOLS[tool](**args, repo=repo)
    except TypeError as e:
        res = {
            "tool": tool, "ok": False, "outcome": "bad_args",
            "answer": f"Could not run {tool}: {e}", "data": {}, "citations": [],
        }
    except Exception as e:  # a broken tool must not kill the loop
        res = {
            "tool": tool, "ok": False, "outcome": "error",
            "answer": f"{tool} failed: {e}", "data": {}, "citations": [],
        }

    v = validator.validate(res)
    qid = memory.record_question(
        mem, question, res.get("answer", ""), res.get("outcome", ""),
        res.get("citations", []), tool, world=world_tag,
    )
    return _envelope(question, res, routing, v, qid, t0)


def _envelope(
    question: str, res: dict, routing: dict, v: dict, qid: str | None, t0: float
) -> dict:
    return {
        "question": question,
        "answer": res.get("answer", ""),
        "outcome": res.get("outcome", "error"),
        "tool": res.get("tool"),
        "ok": bool(res.get("ok")),
        "data": res.get("data", {}),
        "citations": res.get("citations", []),
        "routing": routing,
        "validated": v["ok"],
        "issues": v["issues"],
        "question_id": qid,
        "seconds": round(time.time() - t0, 2),
    }
