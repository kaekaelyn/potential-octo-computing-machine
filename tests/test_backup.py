from __future__ import annotations

import tarfile
from pathlib import Path

from vamp.backup import backup_dir, run_backup
from vamp.config import load_config


def test_backup_dir_defaults_to_desktop_fallback(vamp_home: Path):
    config = load_config(home=vamp_home)

    d = backup_dir(config)

    assert d == config.home / "backups"


def test_backup_dir_honors_explicit_override(vamp_home: Path, tmp_path: Path):
    vamp_home.mkdir(parents=True, exist_ok=True)
    (vamp_home / "env").write_text(f"VAMP_BACKUP_DIR={tmp_path / 'custom-backups'}\n")
    config = load_config(home=vamp_home)

    d = backup_dir(config)

    assert d == tmp_path / "custom-backups"


def test_run_backup_tarballs_db_and_assets(vamp_home: Path):
    config = load_config(home=vamp_home)
    from vamp import db as vamp_db

    conn = vamp_db.get_connection(config.db_path)
    conn.execute("INSERT INTO leads (kind, dedupe_hash, title) VALUES ('gig', 'x', 'Test lead')")
    conn.commit()
    conn.close()

    assets_dir = config.home / "assets" / "bio"
    assets_dir.mkdir(parents=True)
    (assets_dir / "bio.txt").write_text("A short bio.")

    tar_path = run_backup(config)

    assert tar_path.exists()
    assert tar_path.parent == config.home / "backups"
    with tarfile.open(tar_path) as tar:
        names = tar.getnames()
    assert "vamp.db" in names
    assert any(n.startswith("assets/") for n in names)


def test_run_backup_works_even_with_no_assets_dir(vamp_home: Path):
    config = load_config(home=vamp_home)
    from vamp import db as vamp_db

    conn = vamp_db.get_connection(config.db_path)
    conn.close()

    tar_path = run_backup(config)

    assert tar_path.exists()
    with tarfile.open(tar_path) as tar:
        names = tar.getnames()
    assert "vamp.db" in names
