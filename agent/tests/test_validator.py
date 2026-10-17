"""The honesty contract: no number leaves the building unbacked."""

from busfactor.validator import validate


def answered(answer, data=None, citations=None):
    return {
        "outcome": "answered_with_path",
        "answer": answer,
        "data": data or {},
        "citations": citations or [],
    }


def test_refusal_is_exempt():
    r = validate(
        {
            "outcome": "not_in_graph",
            "answer": "nothing in the graph matches Dandan7's 4 notes",
            "data": {},
            "citations": [],
        }
    )
    assert r == {"ok": True, "issues": []}


def test_backed_numbers_pass():
    r = validate(answered("5 modules, 12 knowers", {"modules": 5, "knowers": 12}))
    assert r["ok"] and r["issues"] == []


def test_fabricated_number_is_flagged():
    r = validate(answered("7 modules are stranded", {"modules": 5}))
    assert not r["ok"]
    assert "7" in r["issues"][0]


def test_rounding_inside_tolerance():
    r = validate(answered("mass 12.35", {"mass": 12.3456}))
    assert r["ok"]


def test_small_integers_are_safe():
    # "2" and "1" appear everywhere ("coverage 1 of 2") — allowlisted by design
    r = validate(answered("bus factor 2, 1 island, 0 gaps", {"islands": 9}))
    assert r["ok"]


def test_citations_count_as_backing():
    r = validate(answered("PR #42 introduced it", {}, [{"label": "#42", "kind": "pr"}]))
    assert r["ok"]
