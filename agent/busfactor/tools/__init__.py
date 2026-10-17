"""The eight-tool catalogue — the product's entire action surface.

Console, API, CLI and MCP all dispatch through `TOOLS` here, so every
front door runs identical code (invariant I9).
"""

from __future__ import annotations

from . import functions
from .schemas import TOOL_SCHEMAS

TOOLS = {
    "who_knows": functions.who_knows,
    "critical_people": functions.critical_people,
    "knowledge_islands": functions.knowledge_islands,
    "module_risk": functions.module_risk,
    "simulate_departure": functions.simulate_departure,
    "handover_plan": functions.handover_plan,
    "heal_and_verify": functions.heal_and_verify,
    "recall": functions.recall,
}


def run_tool(name: str, args: dict | None = None, repo: str = "main") -> dict:
    """`repo` names the graph to read; tools never pick it themselves."""
    call = dict(args or {})
    call.pop("repo", None)
    return TOOLS[name](**call, repo=repo)
