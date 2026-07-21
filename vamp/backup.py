"""``vamp backup``: tarball the SQLite DB + vault assets to Android shared
storage, with a desktop fallback path (PLAN.md §10).

On the phone, this only works after ``termux-setup-storage`` has been run
once (it creates ``~/storage/shared``, a symlink into Android's shared
storage granted via the Termux:API permission prompt); docs recommend
pointing Syncthing or a cloud-drive app at the backup folder from there —
Vamp itself stays offline (CLAUDE.md: no cloud services).
"""

from __future__ import annotations

import tarfile
from datetime import UTC, datetime
from pathlib import Path

from vamp.config import Config

TERMUX_SHARED_STORAGE = Path.home() / "storage" / "shared"
SHARED_STORAGE_SUBDIR = "Vamp/backups"
DESKTOP_FALLBACK_SUBDIR = "backups"


def backup_dir(config: Config) -> Path:
    """Where backup tarballs are written: an explicit override
    (``VAMP_BACKUP_DIR`` in ``~/.vamp/env``), Android shared storage if
    ``termux-setup-storage`` has been run, else a folder under the Vamp
    home directory (desktop-dev fallback)."""
    override = config.get("VAMP_BACKUP_DIR")
    if override:
        return Path(override)
    if TERMUX_SHARED_STORAGE.is_dir():
        return TERMUX_SHARED_STORAGE / SHARED_STORAGE_SUBDIR
    return config.home / DESKTOP_FALLBACK_SUBDIR


def run_backup(config: Config, *, at: datetime | None = None) -> Path:
    """Create a timestamped tarball of the DB (+ WAL/SHM sidecars) and the
    vault's assets/epk directories. Returns the tarball's path."""
    dest_dir = backup_dir(config)
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = (at or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    tar_path = dest_dir / f"vamp-backup-{stamp}.tar.gz"

    with tarfile.open(tar_path, "w:gz") as tar:
        if config.db_path.exists():
            tar.add(config.db_path, arcname="vamp.db")
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{config.db_path}{suffix}")
            if sidecar.exists():
                tar.add(sidecar, arcname=f"vamp.db{suffix}")
        for subdir in ("assets", "epk"):
            path = config.home / subdir
            if path.is_dir():
                tar.add(path, arcname=subdir)

    return tar_path
