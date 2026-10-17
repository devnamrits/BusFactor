"""Routing is deterministic when no LLM is configured — test that contract."""

import pytest

from busfactor import planner


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    monkeypatch.setattr(planner.settings, "llm_base_url", "")
    monkeypatch.setattr(planner.settings, "llm_model", "")


def route(q):
    return planner.plan(q)


def test_what_if_leaves_routes_to_drill():
    r = route("What if Roi Lipman leaves?")
    assert r["tool"] == "simulate_departure"
    assert r["args"]["person_ref"] == "Roi Lipman"
    assert r["engine"] == "deterministic"


def test_what_happens_if_routes_to_drill():
    r = route("what happens if Dvir Dukhan quits")
    assert r["tool"] == "simulate_departure"
    assert r["args"]["person_ref"] == "Dvir Dukhan"


def test_who_knows_routes_with_ref():
    r = route("Who knows src/udf?")
    assert r["tool"] == "who_knows"
    assert r["args"]["ref"] == "src/udf"


def test_carry_routes_to_person_lookup():
    r = route("What does Dvir Dukhan carry?")
    assert r["tool"] == "who_knows"
    assert r["args"]["ref"] == "Dvir Dukhan"


def test_critical_phrasings():
    for q in ("who can we least afford to lose?",
              "who is our single point of failure?",
              "what's our bus factor?"):
        assert route(q)["tool"] == "critical_people"


def test_islands_phrasing():
    assert route("where is knowledge stranded?")["tool"] == "knowledge_islands"
    assert route("any orphaned knowledge?")["tool"] == "knowledge_islands"


def test_module_risk_needs_a_target():
    r = route("risk for src/udf")
    assert r["tool"] == "module_risk"
    assert r["args"]["ref"] == "src/udf"


def test_vague_risk_falls_back_to_critical_people():
    assert route("what is our knowledge risk?")["tool"] == "critical_people"


def test_handover_routes():
    assert route("build me a handover plan")["tool"] == "handover_plan"


def test_heal_routes():
    assert route("heal it and verify")["tool"] == "heal_and_verify"


def test_fallback_is_recall_with_full_question():
    q = "what did we decide about graphblas?"
    r = route(q)
    assert r["tool"] == "recall"
    assert r["args"]["question"] == q
