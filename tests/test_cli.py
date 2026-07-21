from __future__ import annotations

import tarfile
from pathlib import Path

import pytest

from vamp import db as vamp_db
from vamp.cli import main
from vamp.config import load_config


def test_backup_subcommand_writes_tarball(vamp_home: Path, monkeypatch, capsys):
    monkeypatch.setenv("VAMP_HOME", str(vamp_home))
    vamp_db.get_connection(load_config(home=vamp_home).db_path).close()

    exit_code = main(["backup"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Backup written to" in out
    tar_path = Path(out.strip().rsplit(" ", 1)[-1])
    assert tar_path.exists()
    with tarfile.open(tar_path) as tar:
        assert "vamp.db" in tar.getnames()


def test_no_subcommand_errors(capsys):
    with pytest.raises(SystemExit) as exc_info:
        main([])
    assert exc_info.value.code != 0
