# BusFactor — self-contained deploy image: FalkorDB + API + console.
#
#   docker build -f deploy/Dockerfile -t busfactor .
#   docker run --rm -p 8000:8000 busfactor
#
# Everything lives in this one image; the pinned demo graph is seeded from
# data/snapshot.json on first boot (see deploy/entrypoint.sh). Used by
# render.yaml (Render free plan), but works on any Docker host.

# ---- stage 1: build the console -------------------------------------------
FROM node:24-bookworm-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/index.html web/vite.config.js ./
COPY web/src ./src
RUN npm run build

# ---- stage 2: FalkorDB runtime + the Python app ---------------------------
# The official image is redis + falkordb.so on Debian; Python comes on top.
# Keep /app as a copy of the repo layout: api.py resolves the console at
# <repo-root>/web/dist, so the package is installed editable from source
# (a regular install would move busfactor/ into site-packages and lose it).
FROM falkordb/falkordb:latest
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 python3-venv git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY agent/pyproject.toml /app/agent/pyproject.toml
COPY agent/busfactor /app/agent/busfactor
RUN python3 -m venv /app/venv \
    && /app/venv/bin/pip install --no-cache-dir --quiet -e /app/agent

COPY data/snapshot.json /app/data/snapshot.json
COPY --from=web /web/dist /app/web/dist
COPY deploy/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENV FALKORDB_HOST=localhost \
    FALKORDB_PORT=6379 \
    SNAPSHOT_PATH=/app/data/snapshot.json \
    PATH=/app/venv/bin:${PATH}

# The image's own entrypoint (run.sh) is intentionally bypassed: this
# container manages FalkorDB and the API together — see entrypoint.sh.
ENTRYPOINT ["/app/entrypoint.sh"]

EXPOSE 8000
