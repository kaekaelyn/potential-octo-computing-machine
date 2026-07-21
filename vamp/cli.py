"""``vamp`` CLI. Currently just ``backup`` (PLAN.md §10/§12 M3); run it
with ``python -m vamp.cli backup`` (the Makefile's ``backup`` target does
this via the dev venv)."""

from __future__ import annotations

import argparse
import sys

from vamp.backup import run_backup
from vamp.config import load_config
from vamp.db import get_connection


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vamp")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("backup", help="Tarball the DB + vault assets to shared storage")
    subparsers.add_parser("seed", help="Import the seeds/ datasets into the DB (idempotent)")
    import_parser = subparsers.add_parser(
        "import-overpass", help="Import OKC-metro places from OpenStreetMap as verified:false"
    )
    import_parser.add_argument(
        "categories",
        nargs="*",
        help="Categories to import (default: all). See vamp/prospects/overpass.py.",
    )

    args = parser.parse_args(argv)
    config = load_config()

    if args.command == "backup":
        tar_path = run_backup(config)
        print(f"Backup written to {tar_path}")
        return 0

    if args.command == "seed":
        from vamp.seeds.loader import ensure_seed_data

        conn = get_connection(config.db_path)
        try:
            result = ensure_seed_data(conn)
        finally:
            conn.close()
        for dataset, n in result.items():
            print(f"{dataset}: {n} loaded/updated")
        return 0

    if args.command == "import-overpass":
        from vamp.prospects.overpass import CATEGORY_QUERIES, OverpassImporter

        categories = args.categories or sorted(CATEGORY_QUERIES.keys())
        conn = get_connection(config.db_path)
        try:
            results = OverpassImporter(conn).import_categories(categories)
        finally:
            conn.close()
        for r in results:
            status = "ok" if r["ok"] else f"FAILED: {r['error']}"
            print(f"{r['category']}: {r['imported']} imported ({r['seen']} seen) — {status}")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
