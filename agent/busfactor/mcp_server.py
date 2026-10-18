"""BusFactor over MCP — the nine domain tools, for coding agents.

Same functions as the HTTP API (I9), routed through the same repo registry.
Reads are safe anywhere; drills and plans write audit nodes but never touch
observed data; heals run inside throwaway worlds.

    claude mcp add busfactor -- uv run python -m busfactor.mcp_server
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from . import repos
from .tools import run_tool

mcp = MCPServer(
    "busfactor",
    instructions=(
        "Knowledge-risk tools for a git repository: who knows what, who is load-bearing, "
        "what happens if someone leaves, and how to fix it. Every answer cites graph evidence."
    ),
)


def _graph(slug: str) -> str:
    return repos.graph_for((slug or "main").strip() or "main")


@mcp.tool()
def list_repos() -> list[dict]:
    """Every repo indexed in this BusFactor instance, with ingest status."""
    return repos.list_repos()


@mcp.tool()
def who_knows(ref: str, repo: str = "main") -> dict:
    """Who knows a module (e.g. 'src/udf'), or what a person carries (name or id)."""
    return run_tool("who_knows", {"ref": ref}, _graph(repo))


@mcp.tool()
def relations(ref: str, repo: str = "main") -> dict:
    """How two or more people relate: shared modules, PRs, decisions and docs."""
    return run_tool("relations", {"ref": ref}, _graph(repo))


@mcp.tool()
def critical_people(repo: str = "main") -> dict:
    """Rank people by what the team loses if they leave: sole knowers + knowledge mass."""
    return run_tool("critical_people", {}, _graph(repo))


@mcp.tool()
def knowledge_islands(repo: str = "main") -> dict:
    """Stranded knowledge: components with modules but no active knower."""
    return run_tool("knowledge_islands", {}, _graph(repo))


@mcp.tool()
def module_risk(ref: str, repo: str = "main") -> dict:
    """Coverage verdict for one module: knowers, weight, decisions touching it."""
    return run_tool("module_risk", {"ref": ref}, _graph(repo))


@mcp.tool()
def simulate_departure(person_ref: str, repo: str = "main") -> dict:
    """Run a departure drill on a clone world. Returns findings with proofs."""
    return run_tool("simulate_departure", {"person_ref": person_ref}, _graph(repo))


@mcp.tool()
def handover_plan(sim_id: str = "", include_resilience: bool = True, repo: str = "main") -> dict:
    """Draft an ordered handover plan from a drill; each step names a teacher and a reason."""
    return run_tool(
        "handover_plan",
        {"sim_id": sim_id or None, "include_resilience": include_resilience},
        _graph(repo),
    )


@mcp.tool()
def heal_and_verify(plan_id: str = "", repo: str = "main") -> dict:
    """Apply a plan in a fresh world, re-run the drill, and report what actually resolved."""
    return run_tool("heal_and_verify", {"plan_id": plan_id or None}, _graph(repo))


@mcp.tool()
def recall(question: str, repo: str = "main") -> dict:
    """Search recorded questions, decisions, runs and findings for a repo."""
    return run_tool("recall", {"question": question}, _graph(repo))


if __name__ == "__main__":
    mcp.run()
