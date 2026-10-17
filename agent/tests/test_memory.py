"""Memory must not nest: repeats resolve to the factual answer, once."""

from busfactor.memory import canonical_answer


def test_plain_answer_is_untouched():
    plain = "Roi Lipman is who you can least afford to lose."
    assert canonical_answer(plain) == plain


def test_single_wrap_is_stripped():
    text = "From memory — I answered this earlier (q-ab12cd): Roi carries 15.95 mass."
    assert canonical_answer(text) == "Roi carries 15.95 mass."


def test_before_variant_is_stripped():
    text = "From memory — I answered this before (q-99f0aa): Dvir is sole on 3 modules."
    assert canonical_answer(text) == "Dvir is sole on 3 modules."


def test_nested_wraps_resolve_to_the_root():
    root = "Roi has 11 sole modules."
    once = f"From memory — I answered this earlier (q-ab12cd): {root}"
    twice = f"From memory — I answered this before (q-77e001): {once}"
    thrice = f"From memory — I answered this earlier (q-0bcd42): {twice}"
    assert canonical_answer(thrice) == root


def test_empty_and_none_are_safe():
    assert canonical_answer("") == ""
    assert canonical_answer(None) == ""
