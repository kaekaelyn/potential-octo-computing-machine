from __future__ import annotations

from datetime import datetime
from pathlib import Path

from vamp import db as vamp_db
from vamp.config import load_config
from vamp.notify import jobs as notify_jobs
from vamp.notify import termux


def _setup(vamp_home: Path, tmp_path: Path, monkeypatch):
    empty_bin_dir = tmp_path / "empty-bin"
    empty_bin_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("PATH", str(empty_bin_dir))  # no termux-notification: falls back to logging
    config = load_config(home=vamp_home)
    conn = vamp_db.get_connection(config.db_path)
    return conn, config


def test_send_morning_digest_logs_and_records_event(vamp_home: Path, tmp_path: Path, monkeypatch):
    conn, config = _setup(vamp_home, tmp_path, monkeypatch)
    try:
        now = datetime(2026, 7, 20, 8, 0, 0)
        result = notify_jobs.send_morning_digest(conn, config, now=now)

        assert result["skipped"] is False
        assert result["notify"].status == termux.STATUS_LOGGED

        row = conn.execute(
            "SELECT * FROM events WHERE kind = 'morning_digest_sent:2026-07-20'"
        ).fetchone()
        assert row is not None
    finally:
        conn.close()


def test_send_morning_digest_is_not_sent_twice_same_day(
    vamp_home: Path, tmp_path: Path, monkeypatch
):
    conn, config = _setup(vamp_home, tmp_path, monkeypatch)
    try:
        now = datetime(2026, 7, 20, 8, 0, 0)
        first = notify_jobs.send_morning_digest(conn, config, now=now)
        second = notify_jobs.send_morning_digest(conn, config, now=now)

        assert first["skipped"] is False
        assert second["skipped"] is True
        assert conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"] == 1
    finally:
        conn.close()


def test_force_bypasses_the_already_sent_guard(vamp_home: Path, tmp_path: Path, monkeypatch):
    conn, config = _setup(vamp_home, tmp_path, monkeypatch)
    try:
        now = datetime(2026, 7, 20, 8, 0, 0)
        notify_jobs.send_morning_digest(conn, config, now=now)
        forced = notify_jobs.send_morning_digest(conn, config, now=now, force=True)

        assert forced["skipped"] is False
        assert conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"] == 2
    finally:
        conn.close()


def test_send_morning_digest_syncs_playbook_activation_reminders(
    vamp_home: Path, tmp_path: Path, monkeypatch
):
    conn, config = _setup(vamp_home, tmp_path, monkeypatch)
    try:
        conn.execute(
            "INSERT INTO playbooks (slug, title, active_months) VALUES (?, ?, ?)",
            ("sub-list", "The Sub List", "7"),
        )
        conn.commit()
        now = datetime(2026, 7, 20, 8, 0, 0)

        result = notify_jobs.send_morning_digest(conn, config, now=now)

        assert "playbook" in result["headline"].lower()
        reminder = conn.execute(
            "SELECT * FROM reminders WHERE ref_kind = 'playbook_activation'"
        ).fetchone()
        assert reminder is not None
    finally:
        conn.close()


def test_send_sunday_sprint_logs_and_records_event(vamp_home: Path, tmp_path: Path, monkeypatch):
    conn, config = _setup(vamp_home, tmp_path, monkeypatch)
    try:
        now = datetime(2026, 7, 19, 18, 0, 0)  # a Sunday
        result = notify_jobs.send_sunday_sprint(conn, config, now=now)

        assert result["skipped"] is False
        assert result["notify"].status == termux.STATUS_LOGGED
        week_key = now.strftime("%G-W%V")
        row = conn.execute(
            "SELECT * FROM events WHERE kind = ?", (f"sprint_notification_sent:{week_key}",)
        ).fetchone()
        assert row is not None
    finally:
        conn.close()


def test_send_sunday_sprint_is_not_sent_twice_same_week(
    vamp_home: Path, tmp_path: Path, monkeypatch
):
    conn, config = _setup(vamp_home, tmp_path, monkeypatch)
    try:
        now = datetime(2026, 7, 19, 18, 0, 0)
        first = notify_jobs.send_sunday_sprint(conn, config, now=now)
        second = notify_jobs.send_sunday_sprint(conn, config, now=now)

        assert first["skipped"] is False
        assert second["skipped"] is True
    finally:
        conn.close()
