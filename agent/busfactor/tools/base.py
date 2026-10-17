"""Shared plumbing for the tool catalogue: envelopes, citations, name resolution.

Keeping this here means every tool returns the same shape and every tool
speaks the same vocabulary for "not found" — the console and the validator
only ever see one contract.
"""

from __future__ import annotations

import re

from ..sim.diff import K
from ..sim.people import list_people
from . import queries


def f2(x: float) -> str:
    """Two decimals, always — keeps answers inside the validator's tolerance."""
    return f"{float(x):.2f}"


def cite(kind: str, id_: str, label: str, detail: str = "") -> dict:
    return {"kind": kind, "id": id_, "label": label, "detail": detail}


def ok(
    tool: str, answer: str, data: dict, citations: list[dict],
    outcome: str = "answered_with_path",
) -> dict:
    return {
        "tool": tool, "ok": True, "outcome": outcome,
        "answer": answer, "data": data, "citations": citations,
    }


def err(tool: str, answer: str, outcome: str = "unknown_entity", data: dict | None = None) -> dict:
    return {
        "tool": tool, "ok": False, "outcome": outcome,
        "answer": answer, "data": data or {}, "citations": [],
    }


def people_hint(repo: str) -> str:
    return "Known people: " + ", ".join(p["name"] for p in list_people(repo))


def clean_ref(ref: str) -> str:
    out = (ref or "").strip().strip("\"'?!. ").strip()
    out = re.sub(r"^(the|our|a|an)\s+", "", out, flags=re.IGNORECASE)
    return re.sub(r"\s+(module|modules|code|codebase|stuff|file|files)\s*$", "", out, flags=re.IGNORECASE)


def resolve_modules(ref: str, repo: str) -> list[dict]:
    """Module name resolution: exact first, then substring; shortest wins."""
    r = clean_ref(ref).lower().removeprefix("m:")
    if not r:
        return []
    mods = [
        {"id": i, "name": n, "path": p or ""}
        for i, n, p in queries.run("modules_all", world=repo)
    ]
    exact = [
        m for m in mods
        if m["name"].lower() in (r, f"m:{r}") or m["path"].lower() == r
    ]
    if exact:
        return exact
    partial = [m for m in mods if r in m["name"].lower() or r in m["path"].lower()]
    partial.sort(key=lambda m: (len(m["name"]), m["name"]))
    return partial


__all__ = ["K", "cite", "clean_ref", "err", "f2", "ok", "people_hint", "resolve_modules"]
