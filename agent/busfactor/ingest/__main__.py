"""CLI: python -m busfactor.ingest build <repo> | load <snapshot.json>"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..config import settings
from .build import WINDOW_DAYS, build_snapshot
from .loader import load_snapshot


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m busfactor.ingest")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="extract a snapshot from a git clone")
    b.add_argument("repo", type=Path)
    b.add_argument("--out", type=Path, default=settings.snapshot_path)
    b.add_argument("--window-days", type=int, default=WINDOW_DAYS)
    b.add_argument("--token", default=None, help="GitHub token for review data (default: $GITHUB_TOKEN)")

    l = sub.add_parser("load", help="load a snapshot into FalkorDB")
    l.add_argument("snapshot", type=Path, nargs="?", default=settings.snapshot_path)
    l.add_argument("--graph", default=None)
    l.add_argument("--force", action="store_true")

    args = ap.parse_args(argv)
    if args.cmd == "build":
        build_snapshot(
            args.repo,
            args.out,
            window_days=args.window_days,
            token=args.token or settings.github_token or None,
        )
    else:
        stats = load_snapshot(
            args.snapshot,
            graph_name=args.graph or settings.main_graph,
            force=args.force,
        )
        print(json.dumps(stats, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
