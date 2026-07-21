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


def test_default_kit_tasks_are_seeded_on_startup(vamp_home: Path):
    client, config = _client(vamp_home)

    conn = vamp_db.get_connection(config.db_path)
    try:
        tasks = conn.execute("SELECT * FROM kit_tasks ORDER BY ord").fetchall()
    finally:
        conn.close()

    assert len(tasks) == 10
    assert tasks[0]["title"] == "Write your bios"
    assert [t["state"] for t in tasks] == ["todo"] * 10

    body = client.get("/kit").get_data(as_text=True)
    assert "Write your bios" in body
    assert "Export the EPK" in body


def test_seeding_kit_tasks_twice_does_not_duplicate(vamp_home: Path):
    config = load_config(home=vamp_home)
    create_app(config)
    create_app(config)  # second app factory call re-runs ensure_default_kit_tasks

    conn = vamp_db.get_connection(config.db_path)
    try:
        count = conn.execute("SELECT COUNT(*) AS n FROM kit_tasks").fetchone()["n"]
    finally:
        conn.close()
    assert count == 10


def test_toggle_marks_task_done_and_back(vamp_home: Path):
    client, config = _client(vamp_home)

    conn = vamp_db.get_connection(config.db_path)
    try:
        first_id = conn.execute("SELECT id FROM kit_tasks ORDER BY ord LIMIT 1").fetchone()["id"]
    finally:
        conn.close()

    toggle = client.post(f"/kit/{first_id}/toggle")
    assert toggle.status_code == 302
    body = client.get("/kit").get_data(as_text=True)
    assert "1 / 10 done" in body

    client.post(f"/kit/{first_id}/toggle")
    body_again = client.get("/kit").get_data(as_text=True)
    assert "0 / 10 done" in body_again


def test_toggle_missing_task_404s(vamp_home: Path):
    client, _config = _client(vamp_home)
    response = client.post("/kit/999/toggle")
    assert response.status_code == 404
