"""Repository registry — the product's front door.

BusFactor is not wired to one snapshot. Any public repo URL, or any local
git clone, can be indexed into its own FalkorDB graph; everything else in
the system (drills, plans, asks, memory) works unchanged against it.

The registry itself is a small graph. Each indexed repo is a `Repo` node
carrying its ingest status, so the UI can show progress while a clone is
still running. Ingest jobs run in a background thread, one at a time.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from . import db
from .config import ROOT, settings

REGISTRY_GRAPH = "busfactor"
DEMO_SLUG = "main"
DEMO_REPO = {
    "slug": DEMO_SLUG,
    "name": "FalkorDB/FalkorDB",
    "url": "https://github.com/FalkorDB/FalkorDB",
    "graph": "main",
    "kind": "pinned snapshot",
}

DEFAULT_SETTINGS = {"window_days": 3650}
_JOB_LOCK = threading.Lock()


def graph_for(slug: str) -> str:
    """Every repo gets its own graph; the demo repo keeps the historical name."""
    return "main" if slug == DEMO_SLUG else f"repo:{slug}"


def slugify(source: str) -> str:
    """`https://github.com/Owner/Name.git` and `~/dev/Name` → stable slug."""
    src = (source or "").strip().rstrip("/")
    m = re.search(r"github\.com[:/]+([^/]+)/([^/]+?)(?:\.git)?$", src)
    name = f"{m.group(1)}-{m.group(2)}" if m else Path(src).name
    return re.sub(r"[^a-z0-9._-]+", "-", name.lower()).strip("-.")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# registry reads
# ---------------------------------------------------------------------------


def ensure_registry() -> None:
    """Idempotent bootstrap: the pinned demo repo is always present."""
    props = {
        **DEMO_REPO,
        "status": "ready",
        "message": "",
        "created_at": _now(),
        "updated_at": _now(),
    }
    db.rw(
        REGISTRY_GRAPH,
        "MERGE (r:Repo {slug:$slug}) ON CREATE SET r.name=$name, r.url=$url, "
        "r.graph=$graph, r.kind=$kind, r.status=$status, r.message=$message, "
        "r.created_at=$created_at, r.updated_at=$updated_at",
        props,
    )


def list_repos() -> list[dict]:
    ensure_registry()
    rows = db.ro(
        REGISTRY_GRAPH,
        "MATCH (r:Repo) RETURN r.slug, r.name, r.url, r.graph, r.kind, r.status, "
        "r.message, r.created_at, r.updated_at, r.people, r.modules, r.commits, "
        "r.snapshot_sha ORDER BY r.created_at",
    ).result_set
    return [
        {
            "slug": slug,
            "name": name,
            "url": url,
            "graph": graph,
            "kind": kind,
            "status": status,
            "message": message or "",
            "created_at": created,
            "updated_at": updated,
            "people": int(people or 0),
            "modules": int(modules or 0),
            "commits": int(commits or 0),
            "snapshot_sha": sha or "",
        }
        for slug, name, url, graph, kind, status, message, created, updated, people,
        modules, commits, sha in rows
    ]


def get_repo(slug: str) -> dict | None:
    return next((r for r in list_repos() if r["slug"] == slug), None)


def _upsert(slug: str, props: dict) -> None:
    body = {**props, "slug": slug, "updated_at": _now()}
    db.rw(
        REGISTRY_GRAPH,
        "MERGE (r:Repo {slug:$slug}) "
        "ON CREATE SET r.created_at = $now "
        "SET r += $body",
        {"slug": slug, "body": body, "now": _now()},
    )


def set_status(slug: str, status: str, message: str = "") -> None:
    _upsert(slug, {"status": status, "message": message[:400]})


def get_settings() -> dict:
    out = dict(DEFAULT_SETTINGS)
    try:
        rows = db.ro(
            REGISTRY_GRAPH, "MATCH (s:Setting) RETURN s.key, s.value"
        ).result_set
    except Exception:  # registry graph not created yet
        return out
    stored = {k: v for k, v in rows}
    try:
        out["window_days"] = int(stored.get("window_days", out["window_days"]))
    except (TypeError, ValueError):
        pass
    return out


def update_settings(values: dict) -> dict:
    rows = [{"key": k, "value": str(v)} for k, v in values.items()]
    if rows:
        db.rw(
            REGISTRY_GRAPH,
            "UNWIND $rows AS r MERGE (s:Setting {key:r.key}) SET s.value = r.value",
            {"rows": rows},
        )
    return get_settings()


# ---------------------------------------------------------------------------
# ingest jobs
# ---------------------------------------------------------------------------


def connect(source: str, window_days: int | None = None, token: str | None = None) -> dict:
    """Register a repo and start indexing it in the background."""
    slug = slugify(source)
    if not slug:
        raise ValueError("cannot derive a repo name from that input")
    src = source.strip()
    local = src.startswith(("/", "~", ".")) or "://" not in src
    if not local and "github.com" not in src:
        raise ValueError("only github URLs or local git paths are supported")

    current = get_repo(slug)
    if current and current["status"] in ("queued", "cloning", "building", "loading"):
        raise RuntimeError(f"'{slug}' is already being indexed")

    _upsert(
        slug,
        {
            "name": slug,
            "url": src,
            "graph": graph_for(slug),
            "kind": "local" if local else "github",
            "status": "queued",
            "message": "",
        },
    )
    cfg = get_settings()
    days = int(window_days or cfg["window_days"])
    threading.Thread(
        target=_ingest_job, args=(slug, src, days, token), daemon=True, name=f"ingest-{slug}"
    ).start()
    return {"slug": slug, "graph": graph_for(slug), "status": "queued"}


def _resolve_local(source: str) -> Path:
    """Accept absolute paths, cwd-relative paths, or paths relative to the repo root."""
    raw = Path(source).expanduser()
    candidates = [raw] if raw.is_absolute() else [raw.resolve(), (ROOT / raw).resolve()]
    for c in candidates:
        if (c / ".git").exists():
            return c
    raise ValueError(f"not a git clone: {raw}")


def _ingest_job(slug: str, source: str, window_days: int, token: str | None) -> None:
    """clone/fetch → build snapshot → load graph. Status lands in the registry."""
    from .ingest.build import build_snapshot
    from .ingest.git import clone_or_fetch
    from .ingest.loader import load_snapshot

    with _JOB_LOCK:
        try:
            local = source.startswith(("/", "~", ".")) or "://" not in source
            if local:
                repo_path = _resolve_local(source)
                _upsert(slug, {"name": repo_path.name})
            else:
                repo_path = settings.source_dir / slug
                set_status(slug, "cloning", f"fetching {source}")
                clone_or_fetch(source, repo_path, log=lambda m: _upsert(slug, {"message": m.strip()}))

            set_status(slug, "building", f"extracting {window_days}d of history")
            snap_path = settings.snapshots_dir / f"{slug}.json"
            build_snapshot(repo_path, snap_path, window_days=window_days, token=token)

            set_status(slug, "loading", "loading graph")
            load_snapshot(snap_path, graph_name=graph_for(slug), force=True)

            body = json.loads(snap_path.read_text(encoding="utf-8"))
            sha = hashlib.sha256(snap_path.read_bytes()).hexdigest()[:12]
            _upsert(
                slug,
                {
                    "status": "ready",
                    "message": "",
                    "people": len(body.get("people", [])),
                    "modules": len(body.get("modules", [])),
                    "commits": sum(int(p.get("commits", 0)) for p in body.get("people", [])),
                    "snapshot_sha": sha,
                },
            )
        except Exception as e:  # surface the reason, never a silent half-state
            set_status(slug, "error", f"{type(e).__name__}: {e}")
