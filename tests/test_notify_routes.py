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


def _no_termux_notification_on_path(monkeypatch, tmp_path: Path) -> None:
    empty_bin_dir = tmp_path / "empty-bin"
    empty_bin_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("PATH", str(empty_bin_dir))


def test_status_page_reports_unavailable_without_termux_api(
    vamp_home: Path, tmp_path: Path, monkeypatch
):
    _no_termux_notification_on_path(monkeypatch, tmp_path)
    client, _config = _client(vamp_home)

    body = client.get("/notify").get_data(as_text=True)

    assert "not found" in body
    assert "Never sent yet" in body


def test_send_digest_now_sends_and_flashes(vamp_home: Path, tmp_path: Path, monkeypatch):
    _no_termux_notification_on_path(monkeypatch, tmp_path)
    client, config = _client(vamp_home)

    response = client.post("/notify/digest/send")
    assert response.status_code == 302

    body = client.get("/notify").get_data(as_text=True)
    assert "Digest sent" in body

    conn = vamp_db.get_connection(config.db_path)
    try:
        row = conn.execute(
            "SELECT * FROM events WHERE kind LIKE 'morning_digest_sent:%'"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None


def test_send_sprint_now_sends_and_flashes(vamp_home: Path, tmp_path: Path, monkeypatch):
    _no_termux_notification_on_path(monkeypatch, tmp_path)
    client, config = _client(vamp_home)

    response = client.post("/notify/sprint/send")
    assert response.status_code == 302

    body = client.get("/notify").get_data(as_text=True)
    assert "Outreach Sprint sent" in body

    conn = vamp_db.get_connection(config.db_path)
    try:
        row = conn.execute(
            "SELECT * FROM events WHERE kind LIKE 'sprint_notification_sent:%'"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
