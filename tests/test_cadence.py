from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from vamp import db as vamp_db
from vamp.config import load_config
from vamp.prospects import cadence, pipeline


def _conn(vamp_home: Path):
    return vamp_db.get_connection(load_config(home=vamp_home).db_path)


def test_follow_up_offsets_are_7_and_21_days():
    assert cadence.FOLLOW_UP_OFFSET_DAYS == (7, 21)


def test_schedule_follow_ups_dates(vamp_home: Path):
    conn = _conn(vamp_home)
    try:
        pid = pipeline.create_prospect(conn, {"name": "X", "category": "hotel"})
        anchor = datetime(2026, 7, 1, 12, 0, 0)
        due = cadence.schedule_follow_ups(conn, pid, "X", from_time=anchor)
        assert due == ["2026-07-08 12:00:00", "2026-07-22 12:00:00"]
    finally:
        conn.close()


def test_in_cooldown_respects_default_and_override(vamp_home: Path):
    conn = _conn(vamp_home)
    try:
        now = datetime(2026, 7, 21, 12, 0, 0)
        recent = (now - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
        # Default 14-day cooldown: touched 3 days ago -> still cooling.
        pid = pipeline.create_prospect(conn, {"name": "Recent", "category": "bar"})
        conn.execute("UPDATE prospects SET last_touch_at = ? WHERE id = ?", (recent, pid))
        conn.commit()
        row = pipeline.get_prospect(conn, pid)
        assert cadence.in_cooldown(row, now) is True
        # Override to 1 day -> no longer cooling.
        conn.execute("UPDATE prospects SET cooldown_days = 1 WHERE id = ?", (pid,))
        conn.commit()
        row = pipeline.get_prospect(conn, pid)
        assert cadence.in_cooldown(row, now) is False
    finally:
        conn.close()


def test_no_last_touch_is_never_in_cooldown(vamp_home: Path):
    conn = _conn(vamp_home)
    try:
        pid = pipeline.create_prospect(conn, {"name": "Fresh", "category": "bar"})
        assert cadence.in_cooldown(pipeline.get_prospect(conn, pid)) is False
    finally:
        conn.close()


def test_outreach_sprint_aggregates(vamp_home: Path):
    conn = _conn(vamp_home)
    try:
        # A pitch drafted and ready.
        p1 = pipeline.create_prospect(conn, {"name": "Ready One", "category": "hotel"})
        pipeline.set_status(conn, p1, "pitch_drafted")
        # A researched prospect awaiting a pitch.
        pipeline.create_prospect(
            conn, {"name": "To Draft", "category": "church", "status": "researched"}
        )
        # A contacted prospect with an overdue follow-up.
        p3 = pipeline.create_prospect(conn, {"name": "Overdue", "category": "bar"})
        pipeline.set_status(conn, p3, "contacted")
        past = datetime(2020, 1, 1, 0, 0, 0)
        cadence.schedule_follow_ups(conn, p3, "Overdue", from_time=past)
        conn.commit()

        sprint = cadence.outreach_sprint(conn, now=datetime(2026, 7, 21, 12, 0, 0))
        assert sprint["summary"]["pitches_ready"] == 1
        assert sprint["summary"]["to_draft"] == 1
        assert sprint["summary"]["follow_ups_due"] == 2  # both offsets are long past
        headline = cadence.sprint_headline(sprint)
        assert "pitches drafted and ready" in headline
        assert "follow-ups due" in headline
    finally:
        conn.close()


def test_empty_sprint_headline():
    empty = {"summary": {"pitches_ready": 0, "follow_ups_due": 0, "to_draft": 0}}
    assert "quiet" in cadence.sprint_headline(empty)
