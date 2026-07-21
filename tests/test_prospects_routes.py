from __future__ import annotations

from pathlib import Path

from vamp import db as vamp_db
from vamp.app import create_app
from vamp.config import load_config
from vamp.prospects import cadence


def _client(vamp_home: Path):
    config = load_config(home=vamp_home)
    app = create_app(config)
    app.testing = True
    return app.test_client(), config


def test_board_shows_seeded_prospects(vamp_home: Path):
    client, _ = _client(vamp_home)
    body = client.get("/prospects").get_data(as_text=True)
    assert "University of Oklahoma School of Dance" in body
    assert "confirm before pitching" in body  # unverified chip present


def test_create_prospect_and_view_detail(vamp_home: Path):
    client, config = _client(vamp_home)
    resp = client.post(
        "/prospects",
        data={"name": "New Venue", "category": "coffee shop", "angle": "quiet mornings"},
    )
    assert resp.status_code == 302
    conn = vamp_db.get_connection(config.db_path)
    try:
        pid = conn.execute("SELECT id FROM prospects WHERE name = 'New Venue'").fetchone()["id"]
    finally:
        conn.close()
    body = client.get(f"/prospects/{pid}").get_data(as_text=True)
    assert "New Venue" in body
    assert "quiet mornings" in body


def test_log_touch_via_route_schedules_follow_ups(vamp_home: Path):
    client, config = _client(vamp_home)
    client.post(
        "/prospects", data={"name": "Touchable", "category": "hotel", "angle": "lobby grand"}
    )
    conn = vamp_db.get_connection(config.db_path)
    try:
        pid = conn.execute("SELECT id FROM prospects WHERE name = 'Touchable'").fetchone()["id"]
    finally:
        conn.close()
    client.post(f"/prospects/{pid}/status", data={"status": "contacted"})
    client.post(
        f"/prospects/{pid}/touch",
        data={"channel": "email", "summary": "pitched", "outcome": "awaiting"},
    )
    conn = vamp_db.get_connection(config.db_path)
    try:
        n = conn.execute(
            "SELECT COUNT(*) AS n FROM reminders WHERE ref_kind = ? AND ref_id = ?",
            (cadence.FOLLOW_UP_REF_KIND, pid),
        ).fetchone()["n"]
    finally:
        conn.close()
    assert n == 2


def test_advance_route_moves_state(vamp_home: Path):
    client, config = _client(vamp_home)
    client.post("/prospects", data={"name": "Mover", "category": "bar", "angle": "x"})
    conn = vamp_db.get_connection(config.db_path)
    try:
        pid = conn.execute("SELECT id FROM prospects WHERE name = 'Mover'").fetchone()["id"]
    finally:
        conn.close()
    client.post(f"/prospects/{pid}/advance")
    conn = vamp_db.get_connection(config.db_path)
    try:
        status = conn.execute("SELECT status FROM prospects WHERE id = ?", (pid,)).fetchone()[
            "status"
        ]
    finally:
        conn.close()
    assert status == "researched"


def test_sprint_page_renders(vamp_home: Path):
    client, _ = _client(vamp_home)
    body = client.get("/prospects/sprint").get_data(as_text=True)
    assert "Outreach Sprint" in body


def test_playbooks_list_and_detail_render(vamp_home: Path):
    client, _ = _client(vamp_home)
    body = client.get("/playbooks").get_data(as_text=True)
    assert "The Free-Improv Arbitrage" in body
    detail = client.get("/playbooks/retirement-circuit").get_data(as_text=True)
    assert "The Retirement Circuit" in detail
    assert "<h2>" in detail  # markdown rendered
