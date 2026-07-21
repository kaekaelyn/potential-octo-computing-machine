from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from vamp import db as vamp_db
from vamp.sources import runner
from vamp.sources.base import NotConfiguredError, RawLead


class _FakeAdapter:
    def __init__(self, leads=None, error=None, state=None):
        self._leads = leads if leads is not None else []
        self._error = error
        self.state_to_persist = state

    def fetch(self):
        if self._error is not None:
            raise self._error
        return self._leads


@pytest.fixture()
def conn(tmp_path: Path):
    connection = vamp_db.get_connection(tmp_path / "vamp.db")
    yield connection
    connection.close()


def _insert_source(
    conn, *, kind="rss", name="Test source", enabled=1, interval_seconds=3600, last_fetch_at=None
):
    cur = conn.execute(
        "INSERT INTO sources (kind, name, config_json, enabled, interval_seconds, last_fetch_at) "
        "VALUES (?, ?, '{}', ?, ?, ?)",
        (kind, name, enabled, interval_seconds, last_fetch_at),
    )
    conn.commit()
    return cur.lastrowid


# ------------------------------------------------------------ default seed --


def test_ensure_default_sources_creates_adzuna_and_usajobs(conn):
    runner.ensure_default_sources(conn)

    rows = conn.execute("SELECT kind FROM sources").fetchall()
    kinds = {row["kind"] for row in rows}
    assert kinds == {"adzuna", "usajobs"}


def test_ensure_default_sources_is_idempotent(conn):
    runner.ensure_default_sources(conn)
    runner.ensure_default_sources(conn)

    count = conn.execute("SELECT COUNT(*) AS n FROM sources").fetchone()["n"]
    assert count == 2


# ------------------------------------------------------------------- due --


def test_disabled_source_never_due(conn):
    _insert_source(conn, enabled=0, last_fetch_at=None)
    assert runner.find_due_sources(conn) == []


def test_never_fetched_source_is_due(conn):
    _insert_source(conn, last_fetch_at=None)
    due = runner.find_due_sources(conn)
    assert len(due) == 1


def test_recently_fetched_source_not_due(conn):
    now = datetime.now(UTC).replace(tzinfo=None)
    recent = (now - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
    _insert_source(conn, interval_seconds=3600, last_fetch_at=recent)

    assert runner.find_due_sources(conn, now=now) == []


def test_overdue_source_is_due(conn):
    now = datetime.now(UTC).replace(tzinfo=None)
    stale = (now - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    _insert_source(conn, interval_seconds=3600, last_fetch_at=stale)

    due = runner.find_due_sources(conn, now=now)
    assert len(due) == 1


# --------------------------------------------------------------- run_source --


def test_run_source_ingests_leads_and_records_success(conn, monkeypatch):
    source_id = _insert_source(conn, name="Fake feed")
    source_row = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()

    fake = _FakeAdapter(leads=[RawLead(title="Sub needed Sunday", url="https://example.org/a")])
    monkeypatch.setattr(runner, "build_adapter", lambda *a, **k: fake)

    stats = runner.run_source(conn, vamp_config=None, source_row=source_row)

    assert stats == {
        "source_id": source_id,
        "name": "Fake feed",
        "ok": True,
        "error": None,
        "raw_count": 1,
        "created_count": 1,
    }
    lead = conn.execute("SELECT * FROM leads WHERE source_id = ?", (source_id,)).fetchone()
    assert lead["title"] == "Sub needed Sunday"
    row = conn.execute(
        "SELECT last_fetch_at, last_success_at, last_error FROM sources WHERE id = ?", (source_id,)
    ).fetchone()
    assert row["last_fetch_at"] is not None
    assert row["last_success_at"] is not None
    assert row["last_error"] is None
    event = conn.execute("SELECT * FROM events WHERE kind = 'source_fetch'").fetchone()
    payload = json.loads(event["payload_json"])
    assert payload["ok"] is True
    assert payload["created_count"] == 1


def test_run_source_persists_adapter_state(conn, monkeypatch):
    source_id = _insert_source(conn, kind="page_watch", name="Watched page")
    source_row = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()

    fake = _FakeAdapter(leads=[], state="deadbeef")
    monkeypatch.setattr(runner, "build_adapter", lambda *a, **k: fake)

    runner.run_source(conn, vamp_config=None, source_row=source_row)

    state = conn.execute(
        "SELECT content_hash FROM source_state WHERE source_id = ?", (source_id,)
    ).fetchone()
    assert state["content_hash"] == "deadbeef"

    # Second run updates the same row rather than inserting a duplicate.
    fake2 = _FakeAdapter(leads=[], state="cafef00d")
    monkeypatch.setattr(runner, "build_adapter", lambda *a, **k: fake2)
    runner.run_source(conn, vamp_config=None, source_row=source_row)
    state_after = conn.execute(
        "SELECT content_hash FROM source_state WHERE source_id = ?", (source_id,)
    ).fetchone()
    assert state_after["content_hash"] == "cafef00d"
    count = conn.execute(
        "SELECT COUNT(*) AS n FROM source_state WHERE source_id = ?", (source_id,)
    ).fetchone()["n"]
    assert count == 1


def test_run_source_records_failure_without_raising(conn, monkeypatch):
    source_id = _insert_source(conn, name="Broken source")
    source_row = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()

    fake = _FakeAdapter(error=NotConfiguredError("no API key set"))
    monkeypatch.setattr(runner, "build_adapter", lambda *a, **k: fake)

    stats = runner.run_source(conn, vamp_config=None, source_row=source_row)

    assert stats["ok"] is False
    assert "no API key set" in stats["error"]
    row = conn.execute("SELECT last_error FROM sources WHERE id = ?", (source_id,)).fetchone()
    assert "no API key set" in row["last_error"]


def test_one_raising_source_does_not_affect_others(conn, monkeypatch):
    """The core M2 acceptance criterion: a raising adapter must not affect
    other sources' polls in the same run."""
    ok_id = _insert_source(conn, name="Good source")
    bad_id = _insert_source(conn, name="Bad source")

    good_adapter = _FakeAdapter(leads=[RawLead(title="Real lead", url="https://example.org/x")])
    bad_adapter = _FakeAdapter(error=RuntimeError("boom"))

    def fake_build_adapter(vamp_config, conn, source_row):
        return bad_adapter if source_row["id"] == bad_id else good_adapter

    monkeypatch.setattr(runner, "build_adapter", fake_build_adapter)

    stats = runner.run_due_sources(conn, vamp_config=None)

    by_id = {s["source_id"]: s for s in stats}
    assert by_id[ok_id]["ok"] is True
    assert by_id[ok_id]["created_count"] == 1
    assert by_id[bad_id]["ok"] is False
    assert "boom" in by_id[bad_id]["error"]

    # The good source's lead landed even though the bad one blew up.
    lead = conn.execute("SELECT * FROM leads WHERE source_id = ?", (ok_id,)).fetchone()
    assert lead is not None
