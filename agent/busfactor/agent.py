"""ask() — one question in, one cited answer out, memory appended.

The loop is deliberately thin: route → run one tool → validate numbers →
record the question. All the intelligence lives in the tools and the graph.
"""

from __future__ import annotations

import time

from . import memory, planner, validator
from .tools import TOOLS


def ask(question: str) -> dict:
    t0 = time.time()
    question = (question or "").strip()
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
    prior = memory.match_question(question)
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
        res = {
            "tool": "recall",
            "ok": True,
            "outcome": "answered_from_memory",
            "answer": f"From memory — I answered this earlier ({prior['id']}): {prior['answer']}",
            "data": {"prior": prior},
            "citations": [{
                "kind": "question",
                "id": prior["id"],
                "label": "earlier question",
                "detail": prior["text"],
            }],
        }
        v = validator.validate(res)
        qid = memory.record_question(
            question, res["answer"], res["outcome"], res["citations"], "recall"
        )
        return _envelope(question, res, routing, v, qid, t0)

    routing = planner.plan(question)
    tool = routing["tool"]
    args = routing.get("args") or {}
    try:
        res = TOOLS[tool](**args)
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
        question, res.get("answer", ""), res.get("outcome", ""),
        res.get("citations", []), tool,
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
