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
from busfactor import db
from busfactor.config import settings
from busfactor.ingest.loader import load_snapshot

if settings.main_graph in db.list_graphs():
    print(f"seed: '{settings.main_graph}' already loaded — skipping")
else:
    stats = load_snapshot(settings.snapshot_path, graph_name=settings.main_graph)
    print(
        f"seed: '{settings.main_graph}' loaded — "
        f"{stats['total_nodes']} nodes · {stats['total_edges']} edges"
    )
PY

exec python -m uvicorn busfactor.api:app --host 0.0.0.0 --port "${PORT:-8000}"
