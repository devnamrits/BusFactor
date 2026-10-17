"""Guardrails: a building graph reads as empty; a mega-repo window fails fast."""

from __future__ import annotations

import subprocess

import pytest
from redis.exceptions import ResponseError

from busfactor.db import _EmptyResult, _is_missing_graph
from busfactor.ingest.git import read_commits


def test_missing_graph_detected():
    assert _is_missing_graph(ResponseError("Invalid graph operation on empty key"))
    assert not _is_missing_graph(ResponseError("syntax error at token 'MATCH'"))


def test_empty_result_reads_as_no_rows():
    result = _EmptyResult()
    assert result.result_set == []
    assert list(result.result_set) == []


def _make_repo(path, commits: int):
    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)

    subprocess.run(["git", "init", "-q", str(path)], check=True)
    for i in range(commits):
        (path / "m.py").write_text(f"x={i}\n")
        git("add", "-A")
        git(
            "-c", "user.name=tester", "-c", "user.email=tester@example.com",
            "commit", "-qm", f"commit {i}",
        )
    return path


def test_read_commits_caps_mega_history(tmp_path):
    repo = _make_repo(tmp_path / "big", commits=3)
    with pytest.raises(ValueError, match="history too large"):
        read_commits(repo, "2000-01-01T00:00:00Z", max_commits=2)


def test_read_commits_streams_normally(tmp_path):
    repo = _make_repo(tmp_path / "small", commits=2)
    commits = read_commits(repo, "2000-01-01T00:00:00Z", max_commits=10)
    assert [c.subject for c in commits] == ["commit 1", "commit 0"]  # newest first
    assert all(c.files == ["m.py"] for c in commits)
