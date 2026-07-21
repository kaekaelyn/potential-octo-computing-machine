"""Config loading from ~/.vamp/env (CLAUDE.md: config from ~/.vamp/env)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_HOME = Path.home() / ".vamp"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8485

ENV_FILE_TEMPLATE = """\
# Vamp config — one KEY=VALUE per line. Lines starting with # are ignored.
# This file lives in Termux private storage and is created mode 600
# because it may hold API keys (Adzuna, USAJOBS) — see PLAN.md §11.
#
# VAMP_DB_PATH=/path/to/vamp.db
# VAMP_HOST=127.0.0.1
# VAMP_PORT=8485
# ADZUNA_APP_ID=
# ADZUNA_APP_KEY=
# USAJOBS_API_KEY=
# USAJOBS_EMAIL=
"""


@dataclass(frozen=True)
class Config:
    home: Path
    db_path: Path
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    values: dict[str, str] = field(default_factory=dict)

    def get(self, key: str, default: str | None = None) -> str | None:
        return self.values.get(key, default)


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def ensure_vamp_home(home: Path) -> Path:
    """Create ~/.vamp (and a starter env file) if it doesn't exist yet."""
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    env_file = home / "env"
    if not env_file.exists():
        env_file.write_text(ENV_FILE_TEMPLATE)
        env_file.chmod(0o600)
    return home


def load_config(home: Path | None = None) -> Config:
    """Load config from ~/.vamp/env, creating defaults if missing.

    Honors $VAMP_HOME so tests and alternate installs can redirect
    everything without touching a real home directory.
    """
    if home is None:
        home = Path(os.environ.get("VAMP_HOME", str(DEFAULT_HOME)))
    ensure_vamp_home(home)
    values = _parse_env_file(home / "env")

    db_path = Path(values.get("VAMP_DB_PATH", str(home / "vamp.db")))
    host = values.get("VAMP_HOST", DEFAULT_HOST)
    port = int(values.get("VAMP_PORT", str(DEFAULT_PORT)))

    return Config(home=home, db_path=db_path, host=host, port=port, values=values)
