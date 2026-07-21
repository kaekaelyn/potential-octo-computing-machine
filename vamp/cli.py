"""``vamp`` CLI. Currently just ``backup`` (PLAN.md §10/§12 M3); run it
with ``python -m vamp.cli backup`` (the Makefile's ``backup`` target does
this via the dev venv)."""

from __future__ import annotations

import argparse
import sys

from vamp.backup import run_backup
from vamp.config import load_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vamp")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("backup", help="Tarball the DB + vault assets to shared storage")

    args = parser.parse_args(argv)
    config = load_config()

    if args.command == "backup":
        tar_path = run_backup(config)
        print(f"Backup written to {tar_path}")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
