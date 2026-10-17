"""Question → tool routing.

Deterministic regex patterns run first: they are testable, explainable and
fast. When an LLM endpoint is configured it gets first refusal and the
deterministic planner is both the system prompt's tool list and the
fallback when the model is down or returns nonsense (invariant I5 — the
model routes, it never writes Cypher).
"""

from __future__ import annotations

import json
import re

import httpx

from .config import settings
from .tools import TOOL_SCHEMAS, TOOLS

_WHATIF = re.compile(
    r"(?:what\s+(?:if|happens?\s+if)|if|simulate|drill)\s+(?:that\s+|our\s+)?"
    r"(.+?)\s+(?:leaves?|left|quits?|resigns?|departs?|leaving|departure|wins\s+the\s+lottery)\b",
    re.IGNORECASE,
)
_WHOKNOWS = re.compile(
    r"who\s+(?:knows|can\s+we\s+ask\s+about|understands?|owns?)\s+(.+?)[\?\.]?$", re.IGNORECASE
)


def _clean_ref(ref: str) -> str:
    out = (ref or "").strip().strip("\"'?!. ").strip()
    return re.sub(r"^(the|our|a|an)\s+", "", out, flags=re.IGNORECASE)


def _heuristic(question: str) -> dict:
    q = question.strip()

    m = _WHATIF.search(q)
    if m:
        return {
            "tool": "simulate_departure",
            "args": {"person_ref": _clean_ref(m.group(1))},
            "reason": "departure question — 'what if … leaves'",
        }
    m = _WHOKNOWS.search(q)
    if m:
        return {
            "tool": "who_knows",
            "args": {"ref": _clean_ref(m.group(1))},
            "reason": "'who knows …'",
        }
    m = re.search(r"what\s+does\s+(.+?)\s+(?:carry|own|work\s+on|know)[\?\.]?$", q, re.IGNORECASE)
    if m:
        return {
            "tool": "who_knows",
            "args": {"ref": _clean_ref(m.group(1))},
            "reason": "'what does … carry'",
        }
    if re.search(
        r"(least afford|indispensable|can'?t lose|cannot lose|most critical|"
        r"key person|critical people|bus factor|single point)",
        q,
        re.IGNORECASE,
    ):
        return {
            "tool": "critical_people",
            "args": {},
            "reason": "criticality question",
        }
    if re.search(r"(stranded|island|orphan(?:ed)?\s+knowledge|no\s+one\s+(?:left\s+)?knows)", q, re.IGNORECASE):
        return {
            "tool": "knowledge_islands",
            "args": {},
            "reason": "stranded-knowledge question",
        }
    if re.search(r"(risk|fragile|fragility|coverage)", q, re.IGNORECASE):
        mm = re.search(r"(?:risk|fragility|coverage)\s+(?:for|of|on)\s+(.+?)[\?\.]?$", q, re.IGNORECASE)
        if not mm:
            mm = re.search(r"^(.+?)\s+(?:risk|fragility|coverage)[\?\.]?$", q, re.IGNORECASE)
        # "src/udf risk" names a module; "what is our risk" names nothing
        if mm and not re.match(
            r"(what|where|how|who|when|why|is|are|was|do|does|our|the|this|any|is\s+any)\b",
            mm.group(1).strip(),
            re.IGNORECASE,
        ):
            return {
                "tool": "module_risk",
                "args": {"ref": _clean_ref(mm.group(1))},
                "reason": "module risk question",
            }
        return {
            "tool": "critical_people",
            "args": {},
            "reason": "risk question → who is critical",
        }
    if re.search(r"(handover|succession|plan|who can take over|take over|replace)", q, re.IGNORECASE):
        return {
            "tool": "handover_plan",
            "args": {},
            "reason": "handover question",
        }
    if re.search(r"\b(heal|verify|fix it)\b", q, re.IGNORECASE):
        return {
            "tool": "heal_and_verify",
            "args": {},
            "reason": "heal/verify question",
        }
    return {
        "tool": "recall",
        "args": {"question": q},
        "reason": "fallback — search memory and graph",
    }


_SYSTEM = (
    "You route questions to tools for a knowledge-graph assistant that knows a "
    "codebase's people, modules and decisions. Reply with ONLY a JSON object: "
    '{"tool": <name>, "args": {...}}. Never write Cypher. Tools:\n'
    + json.dumps(TOOL_SCHEMAS, indent=1)
)


def _llm_route(question: str) -> dict | None:
    r = httpx.post(
        f"{settings.llm_base_url}/chat/completions",
        headers=(
            {"Authorization": f"Bearer {settings.llm_api_key}"}
            if settings.llm_api_key
            else {}
        ),
        json={
            "model": settings.llm_model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": question},
            ],
        },
        timeout=20.0,
    )
    r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"]
    data = json.loads(content[content.find("{"): content.rfind("}") + 1])
    tool = data.get("tool")
    if tool not in TOOLS:
        return None
    return {
        "tool": tool,
        "args": data.get("args") or {},
        "reason": f"LLM router ({settings.llm_model})",
    }


def plan(question: str) -> dict:
    if settings.llm_enabled:
        try:
            r = _llm_route(question)
            if r:
                return {**r, "engine": "llm"}
        except Exception:
            pass
    return {**_heuristic(question), "engine": "deterministic"}
