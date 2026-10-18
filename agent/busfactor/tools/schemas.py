"""Tool schemas — one source of truth for the LLM router and the MCP server."""

from __future__ import annotations

TOOL_SCHEMAS = [
    {
        "name": "who_knows",
        "description": (
            "Who knows a module best? Pass a module (src/udf, graph) or a "
            "person name; returns ranked knowers with PR evidence."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "ref": {
                    "type": "string",
                    "description": "Module name/path or person name",
                }
            },
            "required": ["ref"],
        },
    },
    {
        "name": "critical_people",
        "description": (
            "Rank the team by how much depends on them: knowledge mass and "
            "number of modules where they are the only knower."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "knowledge_islands",
        "description": (
            "Stranded knowledge right now: graph components holding modules "
            "with no active person."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "module_risk",
        "description": (
            "Risk profile of one module: coverage, knowers, attached decisions."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "ref": {"type": "string", "description": "Module name or path"}
            },
            "required": ["ref"],
        },
    },
    {
        "name": "simulate_departure",
        "description": (
            "What-if drill: remove a person in an isolated clone world and "
            "measure exactly what breaks."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "person_ref": {"type": "string", "description": "Person name or id"}
            },
            "required": ["person_ref"],
        },
    },
    {
        "name": "handover_plan",
        "description": (
            "Build a handover plan from the latest drill: who should learn "
            "which module, ranked and explained."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "sim_id": {"type": "string", "description": "Drill to plan from (default latest)"},
                "include_resilience": {
                    "type": "boolean",
                    "description": "Also cover pre-existing single-knower modules",
                },
            },
        },
    },
    {
        "name": "heal_and_verify",
        "description": (
            "Apply the plan in a clone world and re-run every metric — proof "
            "the fix works before anyone gets a ticket."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "plan_id": {"type": "string", "description": "Plan to heal with (default latest)"}
            },
        },
    },
    {
        "name": "recall",
        "description": (
            "Search memory and the graph: earlier questions and runs, "
            "recorded decisions, docs and PRs by topic, a dossier for any "
            "person or module named, and repo-wide counts ('how many…', "
            "'what's in this repo')."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "What to remember about"}
            },
            "required": ["question"],
        },
    },
    {
        "name": "relations",
        "description": (
            "How two or more people relate: shared modules (joint familiarity), "
            "co-authored/reviewed PRs, shared decisions and docs. Pass names "
            "separated by commas or 'and'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "ref": {
                    "type": "string",
                    "description": "Two or more person names, e.g. 'Dvir, Avi and Guy'",
                }
            },
            "required": ["ref"],
        },
    },
]
