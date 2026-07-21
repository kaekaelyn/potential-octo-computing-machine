from __future__ import annotations

from datetime import date
from pathlib import Path

from vamp import db as vamp_db
from vamp.config import load_config
from vamp.scene import service


def _conn(vamp_home: Path):
    return vamp_db.get_connection(load_config(home=vamp_home).db_path)


def _create_event(conn, cadence: dict) -> int:
    return service.create_event(
        conn, {"name": "Test Open Mic", "venue": "Blue Note", "kind": "open_mic"}, cadence
    )


def test_sync_creates_no_reminder_when_not_going(vamp_home: Path):
    conn = _conn(vamp_home)
    try:
        _create_event(conn, {"freq": "weekly", "weekday": "friday"})
        created = service.sync_recap_reminders(conn, today=date(2026, 7, 21))
        assert created == 0
    finally:
        conn.close()


def test_sync_creates_a_reminder_once_going_and_occurrence_passed(vamp_home: Path):
    conn = _conn(vamp_home)
    try:
        event_id = _create_event(conn, {"freq": "weekly", "weekday": "friday"})
        service.toggle_going(conn, event_id)

        created = service.sync_recap_reminders(conn, today=date(2026, 7, 21))
        assert created == 1

        reminders = conn.execute(
            "SELECT * FROM reminders WHERE ref_kind = ? AND ref_id = ?",
            (service.RECAP_REF_KIND, event_id),
        ).fetchall()
        assert len(reminders) == 1
        assert "Test Open Mic" in reminders[0]["message"]

        row = service.get_event(conn, event_id)
        assert row["last_recap_at"] == "2026-07-17"  # the prior Friday
    finally:
        conn.close()


def test_sync_is_idempotent_within_the_same_occurrence(vamp_home: Path):
    conn = _conn(vamp_home)
    try:
        event_id = _create_event(conn, {"freq": "weekly", "weekday": "friday"})
        service.toggle_going(conn, event_id)

        service.sync_recap_reminders(conn, today=date(2026, 7, 21))
        second = service.sync_recap_reminders(conn, today=date(2026, 7, 22))
        assert second == 0

        n = conn.execute(
            "SELECT COUNT(*) AS n FROM reminders WHERE ref_kind = ? AND ref_id = ?",
            (service.RECAP_REF_KIND, event_id),
        ).fetchone()["n"]
        assert n == 1
    finally:
        conn.close()


def test_sync_fires_again_after_the_next_occurrence(vamp_home: Path):
    conn = _conn(vamp_home)
    try:
        event_id = _create_event(conn, {"freq": "weekly", "weekday": "friday"})
        service.toggle_going(conn, event_id)

        service.sync_recap_reminders(conn, today=date(2026, 7, 21))  # prior Friday: 7/17
        service.sync_recap_reminders(conn, today=date(2026, 7, 28))  # prior Friday: 7/24 (new)

        n = conn.execute(
            "SELECT COUNT(*) AS n FROM reminders WHERE ref_kind = ? AND ref_id = ?",
            (service.RECAP_REF_KIND, event_id),
        ).fetchone()["n"]
        assert n == 2
    finally:
        conn.close()


def test_recap_route_logs_a_person_and_dismisses_reminder(vamp_home: Path):
    from vamp.app import create_app

    config = load_config(home=vamp_home)
    app = create_app(config)
    app.testing = True
    client = app.test_client()

    conn = _conn(vamp_home)
    try:
        event_id = _create_event(conn, {"freq": "weekly", "weekday": "friday"})
        service.toggle_going(conn, event_id)
        service.sync_recap_reminders(conn, today=date(2026, 7, 21))
    finally:
        conn.close()

    resp = client.post(
        f"/scene/{event_id}/recap",
        data={"person_name": "Jane Doe", "person_role": "worship leader"},
    )
    assert resp.status_code == 302

    conn = _conn(vamp_home)
    try:
        person = conn.execute("SELECT * FROM people WHERE name = 'Jane Doe'").fetchone()
        assert person is not None
        assert "Test Open Mic" in person["met_at"]
        open_reminders = conn.execute(
            "SELECT COUNT(*) AS n FROM reminders WHERE ref_kind = ? AND ref_id = ? AND done = 0",
            (service.RECAP_REF_KIND, event_id),
        ).fetchone()["n"]
        assert open_reminders == 0
    finally:
        conn.close()


def test_recap_route_dismiss_without_a_name_creates_no_person(vamp_home: Path):
    from vamp.app import create_app

    config = load_config(home=vamp_home)
    app = create_app(config)
    app.testing = True
    client = app.test_client()

    conn = _conn(vamp_home)
    try:
        event_id = _create_event(conn, {"freq": "weekly", "weekday": "friday"})
        service.toggle_going(conn, event_id)
        service.sync_recap_reminders(conn, today=date(2026, 7, 21))
    finally:
        conn.close()

    client.post(f"/scene/{event_id}/recap", data={"person_name": ""})

    conn = _conn(vamp_home)
    try:
        n = conn.execute("SELECT COUNT(*) AS n FROM people").fetchone()["n"]
        assert n == 0
        open_reminders = conn.execute(
            "SELECT COUNT(*) AS n FROM reminders WHERE ref_kind = ? AND ref_id = ? AND done = 0",
            (service.RECAP_REF_KIND, event_id),
        ).fetchone()["n"]
        assert open_reminders == 0
    finally:
        conn.close()
