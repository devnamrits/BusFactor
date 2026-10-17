"""Environment-driven settings. Every knob the system reads lives here."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]

load_dotenv(ROOT / ".env")


class Settings:
    """Plain settings object — no framework, easy to reason about."""

    def __init__(self) -> None:
        # FalkorDB
        self.falkordb_host = os.getenv("FALKORDB_HOST", "localhost")
        self.falkordb_port = int(os.getenv("FALKORDB_PORT", "6379"))
        self.falkordb_username = os.getenv("FALKORDB_USERNAME") or None
        self.falkordb_password = os.getenv("FALKORDB_PASSWORD") or None
        self.main_graph = os.getenv("MAIN_GRAPH", "main")

        # Data
        self.snapshot_path = Path(
            os.getenv("SNAPSHOT_PATH", str(ROOT / "data" / "snapshot.json"))
        )
        self.raw_dir = Path(os.getenv("RAW_DIR", str(ROOT / "data" / "raw")))
        self.source_dir = Path(os.getenv("SOURCE_DIR", str(ROOT / "data" / "source")))
        self.snapshots_dir = Path(
            os.getenv("SNAPSHOTS_DIR", str(ROOT / "data" / "snapshots"))
        )
        self.auto_ingest = os.getenv("AUTO_INGEST", "0") == "1"

        # LLM (optional — a deterministic planner runs when unset)
        self.llm_base_url = os.getenv("LLM_BASE_URL", "").rstrip("/")
        self.llm_model = os.getenv("LLM_MODEL", "")
        self.llm_api_key = os.getenv("LLM_API_KEY", "")

        # GitHub (optional)
        self.github_token = os.getenv("GITHUB_TOKEN", "")
        self.actions_repo = os.getenv("ACTIONS_REPO", "")

        # Product constants
        self.coverage_floor = int(os.getenv("COVERAGE_FLOOR", "2"))  # K in coverage_thin
        # fail-fast net for absurd histories — raise it if you mean it
        self.max_commits = int(os.getenv("BUSFACTOR_MAX_COMMITS", "250000"))

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_base_url and self.llm_model)


settings = Settings()
