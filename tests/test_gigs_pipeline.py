from __future__ import annotations

from datetime import datetime
from pathlib import Path

from vamp import db as vamp_db
from vamp.config import load_config
from vamp.gigs import pipeline


def _conn(vamp_home: Path):
    return vamp_db.get_connection(load_config(home=vamp_home).db_path)


def test_next_state_walks_lifecycle_and_stops_at_paid():
    assert pipeline.next_state("offered") == "confirmed"
    assert pipeline.next_state("confirmed") == "played"
    assert pipeline.next_state("played") == "paid"
    assert pipeline.next_state("paid") is None


def test_create_gig_defaults_to_offered(vamp_home: Path):
    conn = _conn(vamp_home)
    try:
        gig_id = pipeline.create_gig(conn, {"venue": "Vast", "date": "2026-08-01"})
        row = pipeline.get_gig(conn, gig_id)
        assert row["state"] == "offered"
        assert row["played_at"] is None
        assert row["paid_at"] is None
        assert row["strategic"] == 0
    finally:
        conn.close()


def test_advance_walks_the_chain(vamp_home: Path):
    conn = _conn(vamp_home)
    try:
        gig_id = pipeline.create_gig(conn, {"venue": "Vast"})
        pipeline.advance_state(conn, gig_id)
        assert pipeline.get_gig(conn, gig_id)["state"] == "confirmed"
        pipeline.advance_state(conn, gig_id)
        assert pipeline.get_gig(conn, gig_id)["state"] == "played"
    finally:
        conn.close()


def test_marking_played_stamps_played_at_and_schedules_chase_reminder(vamp_home: Path):
    conn = _conn(vamp_home)
    try:
        gig_id = pipeline.create_gig(conn, {"venue": "Vast"})
        anchor = datetime(2026, 7, 1, 20, 0, 0)
        pipeline.set_state(conn, gig_id, "played", now=anchor)

        row = pipeline.get_gig(conn, gig_id)
        assert row["played_at"] == "2026-07-01 20:00:00"

        reminders = conn.execute(
            "SELECT * FROM reminders WHERE ref_kind = ? AND ref_id = ?",
            (pipeline.CHASE_UNPAID_REF_KIND, gig_id),
        ).fetchall()
        assert len(reminders) == 1
        assert reminders[0]["due_at"] == "2026-07-15 20:00:00"  # +14 days
        assert reminders[0]["done"] == 0
    finally:
        conn.close()


def test_marking_paid_stamps_paid_at_and_cancels_chase_reminder(vamp_home: Path):
    conn = _conn(vamp_home)
    try:
        gig_id = pipeline.create_gig(conn, {"venue": "Vast"})
        pipeline.set_state(conn, gig_id, "played", now=datetime(2026, 7, 1))
        pipeline.set_state(conn, gig_id, "paid", now=datetime(2026, 7, 5))

        row = pipeline.get_gig(conn, gig_id)
        assert row["paid_at"] == "2026-07-05 00:00:00"

        open_reminders = conn.execute(
            "SELECT COUNT(*) AS n FROM reminders WHERE ref_kind = ? AND ref_id = ? AND done = 0",
            (pipeline.CHASE_UNPAID_REF_KIND, gig_id),
        ).fetchone()["n"]
        assert open_reminders == 0
    finally:
        conn.close()


def test_delete_gig_cleans_up_invoices_referrals_and_reminders(vamp_home: Path):
    conn = _conn(vamp_home)
    try:
        gig_id = pipeline.create_gig(conn, {"venue": "Vast"})
        pipeline.set_state(conn, gig_id, "played", now=datetime(2026, 7, 1))
        person_id = conn.execute("INSERT INTO people (name) VALUES ('Someone')").lastrowid
        conn.execute("INSERT INTO referrals (person_id, gig_id) VALUES (?, ?)", (person_id, gig_id))
        conn.commit()

        pipeline.delete_gig(conn, gig_id)

        assert pipeline.get_gig(conn, gig_id) is None
        assert (
            conn.execute(
                "SELECT COUNT(*) AS n FROM referrals WHERE gig_id = ?", (gig_id,)
            ).fetchone()["n"]
            == 0
        )
        assert (
            conn.execute(
                "SELECT COUNT(*) AS n FROM reminders "
                "WHERE ref_kind = ? AND ref_id = ? AND done = 0",
                (pipeline.CHASE_UNPAID_REF_KIND, gig_id),
            ).fetchone()["n"]
            == 0
        )
    finally:
        conn.close()


def test_due_chase_reminders_joins_gig_fields(vamp_home: Path):
    conn = _conn(vamp_home)
    try:
        gig_id = pipeline.create_gig(conn, {"venue": "Vast", "date": "2026-07-01"})
        pipeline.set_state(conn, gig_id, "played", now=datetime(2020, 1, 1))
        due = pipeline.due_chase_reminders(conn, now=datetime(2026, 7, 21))
        assert len(due) == 1
        assert due[0]["venue"] == "Vast"
    finally:
        conn.close()
