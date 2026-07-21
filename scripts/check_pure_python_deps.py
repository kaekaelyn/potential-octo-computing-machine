#!/usr/bin/env python3
"""Fail if requirements.txt lists a known-compiled (non-pure-Python) package.

Termux runs Android's bionic libc, so manylinux wheels don't install there
(see CLAUDE.md "Hard rules" / PLAN.md §13). This only checks the *runtime*
requirements file — dev-only tooling (pytest, ruff) lives in
requirements-dev.txt and never has to run on the phone, so it's exempt.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS_FILE = REPO_ROOT / "requirements.txt"

# Packages known to ship compiled extensions with no reliable pure-Python
# path on bionic/Termux. Not exhaustive — if a new dependency needs adding
# and it's compiled, that's a design smell per docs/EXECUTION.md rule 9;
# find the pure-Python route or raise it in PLAN.md instead of trimming
# this list.
KNOWN_COMPILED_PACKAGES = {
    "pydantic-core",
    "pydantic",
    "lxml",
    "uvloop",
    "orjson",
    "ujson",
    "numpy",
    "pandas",
    "scipy",
    "cryptography",
    "cffi",
    "psycopg2",
    "psycopg2-binary",
    "asyncpg",
    "grpcio",
    "greenlet",
    "bcrypt",
    "argon2-cffi",
    "pillow",
    "pyzmq",
    "regex",
    "python-levenshtein",
    "levenshtein",
    "ciso8601",
    "cytoolz",
    "msgpack",
    "yarl",
    "multidict",
    "aiohttp",
    "frozenlist",
    "watchfiles",
    "charset-normalizer",
    "tokenizers",
    "sentencepiece",
    "grpcio-tools",
    "protobuf",
    "brotli",
    "zstandard",
    "duckdb",
    "matplotlib",
}


def _normalize(name: str) -> str:
    return name.strip().lower().replace("_", "-")


def _package_name(requirement_line: str) -> str | None:
    line = requirement_line.split("#", 1)[0].strip()
    if not line or line.startswith(("-", "git+", "http://", "https://")):
        return None
    # Strip environment markers, extras, and version specifiers:
    # "Flask[async]==3.1.3; python_version>='3.11'" -> "Flask"
    line = line.split(";", 1)[0]
    match = re.match(r"^([A-Za-z0-9_.-]+)", line)
    if not match:
        return None
    return _normalize(match.group(1))


def find_compiled_deps(requirements_file: Path = REQUIREMENTS_FILE) -> list[str]:
    if not requirements_file.exists():
        return []
    offenders = []
    for line in requirements_file.read_text().splitlines():
        name = _package_name(line)
        if name and name in KNOWN_COMPILED_PACKAGES:
            offenders.append(name)
    return offenders


def main() -> int:
    offenders = find_compiled_deps()
    if offenders:
        print(
            "ERROR: requirements.txt contains known-compiled package(s) that "
            "won't install on Termux/bionic:\n  " + "\n  ".join(sorted(set(offenders))),
            file=sys.stderr,
        )
        print(
            "See CLAUDE.md 'Pure-Python dependencies only'. Find a pure-Python "
            "alternative or raise the tradeoff in PLAN.md.",
            file=sys.stderr,
        )
        return 1
    print("OK: requirements.txt is free of known-compiled packages.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
