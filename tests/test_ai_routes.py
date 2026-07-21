from __future__ import annotations

from pathlib import Path

from vamp import db as vamp_db
from vamp.app import create_app
from vamp.config import load_config


def _client(vamp_home: Path):
    config = load_config(home=vamp_home)
    app = create_app(config)
    app.testing = True
    return app.test_client(), config


def _no_real_claude_on_path(monkeypatch, tmp_path: Path) -> None:
    """Every AI-triggering route test uses this so it never shells out to a
    real ``claude`` binary that might happen to be on the host PATH — the
    route-level equivalent of the "CLI missing" degradation test."""
    empty_bin_dir = tmp_path / "empty-bin"
    empty_bin_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("PATH", str(empty_bin_dir))


def test_health_page_before_any_check(vamp_home: Path):
    client, _config = _client(vamp_home)
    body = client.get("/ai/health").get_data(as_text=True)
    assert "Never checked yet" in body
    assert "pkg install -y nodejs-lts" in body


def test_check_now_with_missing_cli_reports_missing(vamp_home: Path, tmp_path: Path, monkeypatch):
    _no_real_claude_on_path(monkeypatch, tmp_path)
    client, _config = _client(vamp_home)

    response = client.post("/ai/health/check")
    assert response.status_code == 302

    body = client.get("/ai/health").get_data(as_text=True)
    assert "CLI not found" in body


def test_nightly_run_falls_back_to_heuristics_and_scores_leads(
    vamp_home: Path, tmp_path: Path, monkeypatch
):
    _no_real_claude_on_path(monkeypatch, tmp_path)
    client, config = _client(vamp_home)
    conn = vamp_db.get_connection(config.db_path)
    try:
        conn.execute(
            "INSERT INTO leads (source_id, kind, dedupe_hash, url_hash, title, description, "
            "state) VALUES (NULL, 'gig', 'x', 'y', 'Pianist wanted', 'Solo piano', 'inbox')"
        )
        conn.commit()
    finally:
        conn.close()

    response = client.post("/ai/nightly/run")
    assert response.status_code == 302

    conn = vamp_db.get_connection(config.db_path)
    try:
        row = conn.execute("SELECT * FROM scores").fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row["scorer"] == "none"
