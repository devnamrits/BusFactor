"""Multi-name references parse deterministically — no LLM involved."""

from busfactor.tools.functions import _person_refs


def test_split_on_commas_and_ands():
    assert _person_refs("Dvir, Avi and Guy") == ["Dvir", "Avi", "Guy"]
    assert _person_refs("Dvir and Avi") == ["Dvir", "Avi"]
    assert _person_refs("Dvir & Avi vs Guy") == ["Dvir", "Avi", "Guy"]


def test_strip_relation_leadins_and_punctuation():
    assert _person_refs("relationship between Avi and Guy") == ["Avi", "Guy"]
    assert _person_refs("between Dvir and Avi") == ["Dvir", "Avi"]
    assert _person_refs("Dvir, Avi and Guy?") == ["Dvir", "Avi", "Guy"]
