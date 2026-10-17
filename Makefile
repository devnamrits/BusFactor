# BusFactor — developer commands.
# Works with docker or podman (auto-detected; `RUNTIME=podman make up` to force).

SHELL   := /bin/bash
RUNTIME ?= $(shell command -v docker 2>/dev/null || command -v podman 2>/dev/null || echo docker)
PY      ?= uv run python
DB      ?= busfactor-falkordb
IMAGE   ?= falkordb/falkordb:latest
API     ?= http://localhost:8000

.PHONY: up full-up down ps logs db-shell ingest ingest-live ask api web test fmt bench clean-sims mcp

## ---- stack --------------------------------------------------------------

up: ## start FalkorDB locally (docker or podman)
	@$(RUNTIME) start $(DB) >/dev/null 2>&1 || \
	  $(RUNTIME) run -d --name $(DB) -p 6379:6379 -v busfactor-falkordb-data:/data $(IMAGE) >/dev/null
	@echo "falkordb → localhost:6379"

full-up: ## full stack via compose (falkordb + api + web)
	$(RUNTIME) compose up -d --build

down: ## stop everything
	-@$(RUNTIME) compose down 2>/dev/null || true
	-@$(RUNTIME) rm -f $(DB) >/dev/null 2>&1 || true

ps:
	@$(RUNTIME) ps --filter name=busfactor || true

logs:
	$(RUNTIME) logs -f $(DB)

## ---- data ---------------------------------------------------------------

ingest: ## load the pinned snapshot into FalkorDB
	cd agent && $(PY) -m busfactor.ingest load ../data/snapshot.json --force

ingest-live: ## rebuild the snapshot from the source clone (GITHUB_TOKEN=… for review data)
	cd agent && $(PY) -m busfactor.ingest build ../data/source/falkordb --out ../data/snapshot.json

ingest-live-load: ingest-live ingest ## rebuild and load in one go

## ---- surfaces -----------------------------------------------------------

api: ## run the API locally (hot reload)
	cd agent && uv run uvicorn busfactor.api:app --reload --port 8000

web: ## run the console locally
	cd web && npm run dev

ask: ## ask a question from the CLI: make ask Q="who knows src/udf?"
	cd agent && $(PY) -m busfactor ask "$(Q)"

demo: ## replay the full demo arc (rank → drill → plan → heal)
	cd agent && $(PY) -m busfactor demo

## ---- quality ------------------------------------------------------------

test:
	cd agent && uv run pytest -q

fmt:
	cd agent && uv run ruff format . && uv run ruff check --fix .

bench: ## run the benchmark suite
	cd agent && $(PY) -m busfactor.benchmark run

clean-sims: ## delete all sim:* worlds and run artifacts
	cd agent && $(PY) -m busfactor clean

mcp: ## run the MCP server on stdio
	cd agent && $(PY) -m busfactor.mcp_server
