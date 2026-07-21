from __future__ import annotations

from datetime import date
from pathlib import Path

from vamp import db as vamp_db
from vamp.config import load_config
from vamp.playbooks.activation import (
    PLAYBOOK_ACTIVATION_REF_KIND,
    active_months_list,
    sync_activation_reminders,
)


def _conn(vamp_home: Path):
    return vamp_db.get_connection(load_config(home=vamp_home).db_path)


def test_active_months_list_parses_comma_separated_string():
    assert active_months_list("9,12,1") == [9, 12, 1]


def test_active_months_list_handles_none_and_empty():
    assert active_months_list(None) == []
    assert active_months_list("") == []


def test_active_months_list_ignores_non_numeric_junk():
    assert active_months_list("9, garbage, 1") == [9, 1]


def _add_playbook(conn, slug="sub-list", title="The Sub List", active_months="7"):
    cur = conn.execute(
        "INSERT INTO playbooks (slug, title, active_months) VALUES (?, ?, ?)",
        (slug, title, active_months),
    )
    conn.commit()
    return cur.lastrowid


def test_sync_creates_a_reminder_for_a_playbook_active_this_month(vamp_home: Path):
    conn = _conn(vamp_home)
    try:
        playbook_id = _add_playbook(conn, active_months="7")

        created = sync_activation_reminders(conn, today=date(2026, 7, 21))

        assert created == 1
        row = conn.execute(
            "SELECT * FROM reminders WHERE ref_kind = ? AND ref_id = ?",
            (PLAYBOOK_ACTIVATION_REF_KIND, playbook_id),
        ).fetchone()
        assert row is not None
        assert row["due_at"].startswith("2026-07")
    finally:
        conn.close()


def test_sync_skips_playbooks_not_active_this_month(vamp_home: Path):
    conn = _conn(vamp_home)
    try:
        _add_playbook(conn, active_months="1,2,3")

        created = sync_activation_reminders(conn, today=date(2026, 7, 21))

        assert created == 0
        assert conn.execute("SELECT COUNT(*) AS n FROM reminders").fetchone()["n"] == 0
    finally:
        conn.close()


def test_sync_is_idempotent_within_the_same_month(vamp_home: Path):
    conn = _conn(vamp_home)
    try:
        _add_playbook(conn, active_months="7")

        first = sync_activation_reminders(conn, today=date(2026, 7, 1))
        second = sync_activation_reminders(conn, today=date(2026, 7, 21))

        assert first == 1
        assert second == 0
        assert conn.execute("SELECT COUNT(*) AS n FROM reminders").fetchone()["n"] == 1
    finally:
        conn.close()


def test_sync_creates_a_new_reminder_the_following_active_month(vamp_home: Path):
    conn = _conn(vamp_home)
    try:
        _add_playbook(conn, active_months="1,7")

        sync_activation_reminders(conn, today=date(2026, 1, 15))
        created_july = sync_activation_reminders(conn, today=date(2026, 7, 15))

        assert created_july == 1
        assert conn.execute("SELECT COUNT(*) AS n FROM reminders").fetchone()["n"] == 2
    finally:
        conn.close()
