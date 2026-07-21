from __future__ import annotations

from pathlib import Path

from vamp import db as vamp_db

EXPECTED_TABLES = {
    "sources",
    "leads",
    "requirements",
    "assets",
    "kit_tasks",
    "prospects",
    "touches",
    "people",
    "referrals",
    "scene_events",
    "patrol_items",
    "gigs",
    "invoices",
    "playbooks",
    "scores",
    "reminders",
    "profile",
    "events",
    "source_state",
    "repertoire_items",
}


def _table_names(conn) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {row["name"] for row in rows}


def test_migrate_creates_schema(tmp_path: Path):
    conn = vamp_db.get_connection(tmp_path / "vamp.db")
    try:
        assert EXPECTED_TABLES <= _table_names(conn)
    finally:
        conn.close()


def test_migrate_is_idempotent(tmp_path: Path):
    db_path = tmp_path / "vamp.db"
    conn = vamp_db.get_connection(db_path)
    conn.close()

    # Reopening (which re-runs migrate()) must not error or duplicate tables.
    conn = vamp_db.get_connection(db_path)
    try:
        applied = vamp_db.applied_migrations(conn)
        assert applied == {
            "0001_init.sql",
            "0002_capture_fields.sql",
            "0003_sources_scheduling.sql",
            "0004_requirements_vault.sql",
            "0005_prospects_engine.sql",
            "0006_ai_layer.sql",
            "0007_money_scene_people.sql",
        }
    finally:
        conn.close()


def test_wal_mode_enabled(tmp_path: Path):
    conn = vamp_db.get_connection(tmp_path / "vamp.db")
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"
    finally:
        conn.close()


def test_leads_table_accepts_a_row(tmp_path: Path):
    conn = vamp_db.get_connection(tmp_path / "vamp.db")
    try:
        conn.execute(
            "INSERT INTO leads (kind, dedupe_hash, title) VALUES (?, ?, ?)",
            ("gig", "abc123", "Solo piano, Friday night"),
        )
        conn.commit()
        row = conn.execute("SELECT title, state FROM leads").fetchone()
        assert row["title"] == "Solo piano, Friday night"
        assert row["state"] == "inbox"
    finally:
        conn.close()
