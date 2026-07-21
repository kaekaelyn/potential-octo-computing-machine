from __future__ import annotations

from datetime import datetime
from pathlib import Path

from vamp import db as vamp_db
from vamp.app import create_app
from vamp.config import load_config
from vamp.gigs import pipeline as gigs_pipeline
from vamp.prospects import cadence as prospects_cadence
from vamp.prospects import pipeline as prospects_pipeline


def _client(vamp_home: Path):
    config = load_config(home=vamp_home)
    app = create_app(config)
    app.testing = True
    return app.test_client(), config


def test_reminders_page_lists_gig_chase_unpaid(vamp_home: Path):
    client, config = _client(vamp_home)
    conn = vamp_db.get_connection(config.db_path)
    try:
        gig_id = gigs_pipeline.create_gig(conn, {"venue": "Vast", "date": "2026-01-01"})
        gigs_pipeline.set_state(conn, gig_id, "played", now=datetime(2020, 1, 1))
    finally:
        conn.close()

    body = client.get("/reminders").get_data(as_text=True)
    assert "Chase unpaid" in body
    assert "Vast" in body


def test_reminders_page_lists_prospect_follow_ups(vamp_home: Path):
    client, config = _client(vamp_home)
    conn = vamp_db.get_connection(config.db_path)
    try:
        pid = prospects_pipeline.create_prospect(
            conn, {"name": "The Jones Assembly", "category": "bar"}
        )
        prospects_cadence.schedule_follow_ups(
            conn, pid, "The Jones Assembly", from_time=datetime(2020, 1, 1)
        )
        conn.commit()
    finally:
        conn.close()

    body = client.get("/reminders").get_data(as_text=True)
    assert "Follow up: The Jones Assembly" in body


def test_mark_done_removes_reminder_from_page(vamp_home: Path):
    client, config = _client(vamp_home)
    conn = vamp_db.get_connection(config.db_path)
    try:
        gig_id = gigs_pipeline.create_gig(conn, {"venue": "Vast", "date": "2026-01-01"})
        gigs_pipeline.set_state(conn, gig_id, "played", now=datetime(2020, 1, 1))
        reminder_id = conn.execute(
            "SELECT id FROM reminders WHERE ref_kind = ? AND ref_id = ?",
            (gigs_pipeline.CHASE_UNPAID_REF_KIND, gig_id),
        ).fetchone()["id"]
    finally:
        conn.close()

    resp = client.post(f"/reminders/{reminder_id}/done")
    assert resp.status_code == 302

    body = client.get("/reminders").get_data(as_text=True)
    assert "Chase unpaid" not in body


def test_empty_reminders_page_renders(vamp_home: Path):
    client, _ = _client(vamp_home)
    body = client.get("/reminders").get_data(as_text=True)
    assert "quiet" in body
