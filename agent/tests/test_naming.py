"""Tokenization and repo naming — the cheap invariants memory and registry rely on."""

from busfactor.memory import _tokens
from busfactor.repos import graph_for, slugify


def test_stopwords_and_short_tokens_drop():
    assert _tokens("a b c") == []
    assert _tokens("who knows the module") == ["module"]


def test_names_and_paths_survive():
    assert _tokens("What does Dvir Dukhan carry?") == ["dvir", "dukhan", "carry"]
    assert _tokens("who knows src/udf?") == ["src/udf"]


def test_digits_in_names_are_fine():
    # real handles like Dandan7 must survive tokenization
    assert "dandan7" in _tokens("what does Dandan7 carry?")


def test_github_urls_become_owner_name_slugs():
    assert slugify("https://github.com/FalkorDB/FalkorDB.git") == "falkordb-falkordb"
    assert slugify("https://github.com/sindresorhus/is-odd/") == "sindresorhus-is-odd"


def test_local_paths_become_dir_names():
    assert slugify("/home/dev/code/MyRepo") == "myrepo"
    assert slugify("~/work/analytics-api") == "analytics-api"


def test_graph_naming_keeps_demo_legacy_name():
    assert graph_for("main") == "main"
    assert graph_for("falkordb") == "repo:falkordb"
