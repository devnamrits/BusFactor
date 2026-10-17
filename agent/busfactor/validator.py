"""No unsupported numbers leave the building.

Deterministic templates build answers from tool data, so this normally
passes trivially. When an LLM is wired in it is the guard that stops
fabricated figures — the honesty invariant, enforced in code.
"""

from __future__ import annotations

import json
import re

_NUM = re.compile(r"\d+(?:\.\d+)?")
_ALLOW = {0.0, 1.0, 2.0}


def _nums(text: str) -> list[float]:
    return [float(x) for x in _NUM.findall(text or "")]


def validate(result: dict) -> dict:
    # Refusals and errors assert nothing numeric — only answered claims get checked.
    if result.get("outcome") not in ("answered_with_path", "answered_from_memory"):
        return {"ok": True, "issues": []}
    payload = json.dumps(
        {k: result.get(k) for k in ("data", "citations")}, default=str
    )
    vocab = _nums(payload)
    issues = []
    for n in _nums(result.get("answer", "")):
        if n in _ALLOW:
            continue
        if not any(abs(n - v) <= 0.011 for v in vocab):
            issues.append(f"number {n:g} in the answer is not backed by tool data")
    return {"ok": not issues, "issues": issues}
