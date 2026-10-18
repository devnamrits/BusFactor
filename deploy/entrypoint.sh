#!/usr/bin/env bash
# Container boot — FalkorDB in the background, the pinned demo graph seeded
# on first boot, then the API in the foreground.
#
# Hosted instances have an ephemeral filesystem: every cold start re-seeds
# `main` from the snapshot baked into the image. Repos ingested during a
# previous life are intentionally gone.

set -euo pipefail

FALKORDB_BIN="${FALKORDB_BIN_PATH:-/var/lib/falkordb/bin}"
FALKORDB_DATA="${FALKORDB_DATA_PATH:-/var/lib/falkordb/data}"
mkdir -p "$FALKORDB_DATA"

echo "boot: starting falkordb"
redis-server \
  --bind 127.0.0.1 \
  --dir "$FALKORDB_DATA" \
  --save "" --appendonly no \
  --loadmodule "$FALKORDB_BIN/falkordb.so" \
  MAX_QUEUED_QUERIES 25 TIMEOUT 1000 RESULTSET_SIZE 10000 &

for _ in $(seq 1 120); do
  redis-cli ping >/dev/null 2>&1 && break
  sleep 0.5
done
redis-cli ping >/dev/null 2>&1 || { echo "boot: falkordb did not answer" >&2; exit 1; }
echo "boot: falkordb is up"

python - <<'PY'
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from busfactor import db, repos
from busfactor.config import settings
from busfactor.ingest.loader import load_snapshot

# Shipped snapshots: the pinned demo graph (required) plus pre-indexed
# extras (best-effort) — a free CPU cannot clone Elasticsearch in any
# reasonable time, so hosted judges get the ready graph, not a queue.
SHIPPED = [
    (settings.main_graph, settings.main_graph, Path(settings.snapshot_path), True),
    (
        "elastic-elasticsearch",
        "repo:elastic-elasticsearch",
        Path("/app/data/snapshots/elastic-elasticsearch.json"),
        False,
    ),
]


def register(slug: str, graph: str, path: Path) -> None:
    """Registry row for a shipped graph — same shape a finished job writes."""
    body = json.loads(path.read_text(encoding="utf-8"))
    meta = body.get("meta") or {}
    url = meta.get("repo_url") or ""
    m = re.search(r"github\.com[:/]+([^/]+)/([^/]+?)(?:\.git)?/?$", url)
    name = f"{m.group(1)}/{m.group(2)}" if m else slug
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    db.rw(
        repos.REGISTRY_GRAPH,
        "MERGE (r:Repo {slug:$slug}) ON CREATE SET r.created_at=$now "
        "SET r.name=$name, r.url=$url, r.graph=$graph, r.kind=$kind, "
        "r.status='ready', r.message='', r.people=$people, r.modules=$modules, "
        "r.commits=$commits, r.snapshot_sha=$sha, r.updated_at=$now",
        {
            "slug": slug,
            "name": name,
            "url": url,
            "graph": graph,
            "kind": "pinned snapshot",
            "people": len(body.get("people", [])),
            "modules": len(body.get("modules", [])),
            "commits": sum(int(p.get("commits", 0)) for p in body.get("people", [])),
            "sha": hashlib.sha256(path.read_bytes()).hexdigest()[:12],
            "now": now,
        },
    )


repos.ensure_registry()  # the demo repo is always first in the registry

for slug, graph, path, required in SHIPPED:
    try:
        if graph in db.list_graphs():
            print(f"seed: '{graph}' already loaded — skipping")
        elif path.exists():
            stats = load_snapshot(path, graph_name=graph)
            print(
                f"seed: '{graph}' loaded — "
                f"{stats['total_nodes']} nodes · {stats['total_edges']} edges"
            )
        elif required:
            raise FileNotFoundError(f"required snapshot missing: {path}")
        else:
            print(f"seed: '{graph}' snapshot not shipped — skipping")
            continue
        if graph != settings.main_graph:
            register(slug, graph, path)
    except Exception as e:  # extras never take the demo down; main fails loud
        if required:
            raise
        print(f"seed: '{graph}' skipped — {type(e).__name__}: {e}", flush=True)
PY

exec python -m uvicorn busfactor.api:app --host 0.0.0.0 --port "${PORT:-8000}"
