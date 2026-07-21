from __future__ import annotations

from pathlib import Path

from vamp.config import DEFAULT_HOST, DEFAULT_PORT, load_config


def test_load_config_creates_vamp_home_and_env_file(vamp_home: Path):
    assert not vamp_home.exists()

    config = load_config(home=vamp_home)

    assert vamp_home.is_dir()
    env_file = vamp_home / "env"
    assert env_file.exists()
    assert oct(env_file.stat().st_mode)[-3:] == "600"
    assert config.host == DEFAULT_HOST
    assert config.port == DEFAULT_PORT
    assert config.db_path == vamp_home / "vamp.db"


def test_load_config_reads_overrides(vamp_home: Path):
    vamp_home.mkdir(parents=True)
    (vamp_home / "env").write_text(
        "VAMP_HOST=0.0.0.0\nVAMP_PORT=9999\n# a comment\nADZUNA_APP_ID=abc123\n"
    )

    config = load_config(home=vamp_home)

    assert config.host == "0.0.0.0"
    assert config.port == 9999
    assert config.get("ADZUNA_APP_ID") == "abc123"
    assert config.get("MISSING_KEY", "fallback") == "fallback"


def test_load_config_is_idempotent(vamp_home: Path):
    first = load_config(home=vamp_home)
    (vamp_home / "env").write_text("VAMP_PORT=1234\n")
    second = load_config(home=vamp_home)

    assert first.port == DEFAULT_PORT
    assert second.port == 1234
