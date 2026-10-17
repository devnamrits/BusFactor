"""Optional GitHub enrichment: merged PR titles/authors, and reviews with a token.

Everything is cached per repo under data/snapshots/raw/<slug>/ — snapshot builds
are deterministic and re-runs never re-hit the network. Tokenless runs still work:
the public API allows a few unauthenticated calls per hour, enough for the PR index
(title, author, merge date). Review data requires a token; without one the snapshot
notes `reviews_available: false` and the weight formula renormalizes.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx

API = "https://api.github.com"


def _get(
    url: str,
    cache_file: Path,
    token: str | None,
    params: dict | None = None,
):
    """Cache-first GET. Returns None when rate-limited — callers degrade."""
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text())
        except json.JSONDecodeError:
            pass  # corrupt cache — refetch
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "busfactor-ingest",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = httpx.get(url, headers=headers, params=params, timeout=30)
    except httpx.HTTPError:
        return None
    if r.status_code in (401, 403, 429):
        return None
    r.raise_for_status()
    data = r.json()
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(data))
    return data


def fetch_merged_pulls(
    owner: str,
    name: str,
    since_iso: str,
    cache_dir: Path,
    token: str | None = None,
    max_pages: int = 12,
) -> list[dict]:
    """Merged PRs since `since_iso`, oldest first. Deterministic given cache."""
    merged: list[dict] = []
    for page in range(1, max_pages + 1):
        data = _get(
            f"{API}/repos/{owner}/{name}/pulls",
            cache_dir / f"pulls_page_{page}.json",
            token,
            params={
                "state": "closed",
                "sort": "updated",
                "direction": "desc",
                "per_page": 100,
                "page": page,
            },
        )
        if not data or not isinstance(data, list):
            break
        for pr in data:
            merged_at = pr.get("merged_at")
            if merged_at and merged_at >= since_iso:
                merged.append(
                    {
                        "number": int(pr["number"]),
                        "title": (pr.get("title") or "").strip(),
                        "author_login": ((pr.get("user") or {}).get("login") or "").lower(),
                        "merged_at": merged_at,
                        "url": pr.get("html_url") or "",
                        "changed_files": int(pr.get("changed_files") or 0),
                        "additions": int(pr.get("additions") or 0),
                        "deletions": int(pr.get("deletions") or 0),
                    }
                )
        # pages are sorted by updated_at desc: once an entire page predates the
        # window, everything after it does too (merged_at <= updated_at).
        oldest_updated = min((pr.get("updated_at") or "") for pr in data)
        if oldest_updated and oldest_updated < since_iso:
            break
        if len(data) < 100:
            break
    return sorted(merged, key=lambda p: (p["merged_at"], p["number"]))


def fetch_reviews(
    owner: str,
    name: str,
    number: int,
    cache_dir: Path,
    token: str | None,
) -> list[dict]:
    """Approved reviews for a PR. Token required — returns [] without one."""
    if not token:
        return []
    data = _get(
        f"{API}/repos/{owner}/{name}/pulls/{number}/reviews",
        cache_dir / f"reviews_{number}.json",
        token,
        params={"per_page": 100},
    )
    out: list[dict] = []
    for rv in data or []:
        if rv.get("state") == "APPROVED" and rv.get("user"):
            login = (rv["user"].get("login") or "").lower()
            if login:
                out.append({"login": login, "at": rv.get("submitted_at") or ""})
    return sorted(out, key=lambda r: (r["at"], r["login"]))
