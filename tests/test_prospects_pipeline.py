from __future__ import annotations

from pathlib import Path

from vamp import db as vamp_db
from vamp.config import load_config
from vamp.prospects import cadence, pipeline


def _conn(vamp_home: Path):
    return vamp_db.get_connection(load_config(home=vamp_home).db_path)


def test_next_state_walks_pipeline_and_stops_at_booked():
    assert pipeline.next_state("identified") == "researched"
    assert pipeline.next_state("in_conversation") == "booked"
    # From booked the human chooses recurring vs dead — no auto-advance.
    assert pipeline.next_state("booked") is None
    assert pipeline.next_state("recurring") is None
    assert pipeline.next_state("dead") is None


def test_create_and_advance(vamp_home: Path):
    conn = _conn(vamp_home)
    try:
        pid = pipeline.create_prospect(
            conn,
            {"name": "The Jones Assembly", "category": "listening room", "angle": "jazz brunch"},
        )
        row = pipeline.get_prospect(conn, pid)
        assert row["status"] == "identified"
        assert row["verified"] == 0
        pipeline.advance_status(conn, pid)
        assert pipeline.get_prospect(conn, pid)["status"] == "researched"
    finally:
        conn.close()


def test_log_touch_schedules_two_follow_ups_and_sets_next_touch(vamp_home: Path):
    conn = _conn(vamp_home)
    try:
        pid = pipeline.create_prospect(conn, {"name": "Skirvin", "category": "hotel"})
        pipeline.set_status(conn, pid, "contacted")
        pipeline.log_touch(conn, pid, channel="email", summary="sent pitch", outcome="awaiting")
        reminders = conn.execute(
            "SELECT due_at FROM reminders WHERE ref_kind = ? AND ref_id = ? ORDER BY due_at",
            (cadence.FOLLOW_UP_REF_KIND, pid),
        ).fetchall()
        assert len(reminders) == 2
        row = pipeline.get_prospect(conn, pid)
        assert row["last_touch_at"] is not None
        assert row["next_touch_at"] == reminders[0]["due_at"]  # earliest follow-up
    finally:
        conn.close()


def test_new_touch_supersedes_old_follow_ups(vamp_home: Path):
    conn = _conn(vamp_home)
    try:
        pid = pipeline.create_prospect(conn, {"name": "Gaillardia", "category": "country club"})
        pipeline.set_status(conn, pid, "contacted")
        pipeline.log_touch(conn, pid, channel="email", summary="pitch", outcome="awaiting")
        pipeline.log_touch(conn, pid, channel="email", summary="follow up", outcome="awaiting")
        open_count = conn.execute(
            "SELECT COUNT(*) AS n FROM reminders WHERE ref_kind = ? AND ref_id = ? AND done = 0",
            (cadence.FOLLOW_UP_REF_KIND, pid),
        ).fetchone()["n"]
        assert open_count == 2  # old pair cancelled, fresh pair scheduled
    finally:
        conn.close()


def test_terminal_state_cancels_follow_ups(vamp_home: Path):
    conn = _conn(vamp_home)
    try:
        pid = pipeline.create_prospect(conn, {"name": "Dead End", "category": "bar"})
        pipeline.set_status(conn, pid, "contacted")
        pipeline.log_touch(conn, pid, channel="email", summary="pitch", outcome="awaiting")
        pipeline.set_status(conn, pid, "dead")
        open_count = conn.execute(
            "SELECT COUNT(*) AS n FROM reminders WHERE ref_kind = ? AND ref_id = ? AND done = 0",
            (cadence.FOLLOW_UP_REF_KIND, pid),
        ).fetchone()["n"]
        assert open_count == 0
        assert pipeline.get_prospect(conn, pid)["next_touch_at"] is None
    finally:
        conn.close()


def test_touch_without_scheduling_leaves_cadence_untouched(vamp_home: Path):
    conn = _conn(vamp_home)
    try:
        pid = pipeline.create_prospect(conn, {"name": "Inbound", "category": "church"})
        pipeline.log_touch(
            conn,
            pid,
            channel="email",
            summary="they replied",
            outcome="interested",
            schedule_follow_ups=False,
        )
        n = conn.execute("SELECT COUNT(*) AS n FROM reminders WHERE ref_id = ?", (pid,)).fetchone()[
            "n"
        ]
        assert n == 0
    finally:
        conn.close()
