from __future__ import annotations

from pathlib import Path

from vamp import db as vamp_db
from vamp.app import create_app
from vamp.config import load_config
from vamp.sources import catchup


def _insert_source(conn, *, enabled=1, interval_seconds=3600, last_fetch_at=None):
    cur = conn.execute(
        "INSERT INTO sources (kind, name, config_json, enabled, interval_seconds, last_fetch_at) "
        "VALUES ('rss', 'Test feed', ?, ?, ?, ?)",
        ("{}", enabled, interval_seconds, last_fetch_at),
    )
    conn.commit()
    return cur.lastrowid


def test_no_overdue_sources_returns_none(vamp_home: Path, monkeypatch):
    config = load_config(home=vamp_home)
    conn = vamp_db.get_connection(config.db_path)
    conn.execute("UPDATE sources SET enabled = 0")  # defaults are freshly seeded, mark them off
    conn.commit()
    conn.close()

    result = catchup.trigger_catch_up_if_overdue(config, background=False)

    assert result is None


def test_overdue_source_gets_polled_synchronously(vamp_home: Path, monkeypatch):
    config = load_config(home=vamp_home)
    conn = vamp_db.get_connection(config.db_path)
    conn.execute("UPDATE sources SET enabled = 0")  # silence the seeded defaults
    conn.commit()
    _insert_source(conn, last_fetch_at=None)
    conn.close()

    calls = []
    monkeypatch.setattr(
        "vamp.sources.runner.run_due_sources", lambda conn, cfg, **kw: calls.append(1) or []
    )

    catchup.trigger_catch_up_if_overdue(config, background=False)

    assert calls == [1]


def test_second_call_while_running_is_skipped(vamp_home: Path, monkeypatch):
    config = load_config(home=vamp_home)
    conn = vamp_db.get_connection(config.db_path)
    conn.execute("UPDATE sources SET enabled = 0")
    conn.commit()
    _insert_source(conn, last_fetch_at=None)
    conn.close()

    catchup._catchup_lock.acquire()
    try:
        result = catchup.trigger_catch_up_if_overdue(config, background=False)
        assert result is None
    finally:
        catchup._catchup_lock.release()


def test_page_load_triggers_catchup_synchronously(vamp_home: Path, monkeypatch):
    config = load_config(home=vamp_home)
    app = create_app(config, catchup_sync=True)
    app.testing = True
    conn = vamp_db.get_connection(config.db_path)
    conn.execute("UPDATE sources SET enabled = 0")
    conn.commit()
    _insert_source(conn, last_fetch_at=None)
    conn.close()

    client = app.test_client()
    client.get("/healthz")

    conn = vamp_db.get_connection(config.db_path)
    row = conn.execute("SELECT last_fetch_at FROM sources WHERE kind = 'rss'").fetchone()
    conn.close()
    assert row["last_fetch_at"] is not None
