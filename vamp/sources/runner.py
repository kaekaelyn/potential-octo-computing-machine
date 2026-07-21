"""Runs source adapters against the ``sources`` table: fetch, ingest through
the M1 filters/dedupe, record a fetch result, and log an ``events`` row —
one source at a time, so a raising adapter can never affect the others
(PLAN.md §12 M2 acceptance criterion).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

from vamp.config import Config
from vamp.leads import service as leads_service
from vamp.sources.adzuna import DEFAULT_QUERIES as ADZUNA_DEFAULT_QUERIES
from vamp.sources.adzuna import DEFAULT_RADIUS_MILES, DEFAULT_WHERE
from vamp.sources.registry import build_adapter
from vamp.sources.usajobs import DEFAULT_KEYWORDS as USAJOBS_DEFAULT_KEYWORDS

# Adapters that need real credentials poll less often than the phone's
# battery would like anyway; RSS/page-watch intervals are per-source.
DEFAULT_API_INTERVAL_SECONDS = 6 * 3600

DEFAULT_SOURCES = [
    {
        "kind": "adzuna",
        "name": "Adzuna: musician/pianist/keyboardist/accompanist OKC",
        "config": {
            "where": DEFAULT_WHERE,
            "radius_miles": DEFAULT_RADIUS_MILES,
            "queries": list(ADZUNA_DEFAULT_QUERIES),
        },
        "interval_seconds": DEFAULT_API_INTERVAL_SECONDS,
    },
    {
        "kind": "usajobs",
        "name": "USAJOBS: military band / musician series",
        "config": {"keywords": list(USAJOBS_DEFAULT_KEYWORDS)},
        "interval_seconds": DEFAULT_API_INTERVAL_SECONDS,
    },
]


def ensure_default_sources(conn: sqlite3.Connection) -> None:
    """Idempotently seed the Adzuna/USAJOBS source rows so /sources has
    something to show and enable/disable out of the box. RSS feeds and
    page-watch targets have no sensible default and are added by hand."""
    for spec in DEFAULT_SOURCES:
        existing = conn.execute(
            "SELECT id FROM sources WHERE kind = ? AND name = ?", (spec["kind"], spec["name"])
        ).fetchone()
        if existing:
            continue
        conn.execute(
            "INSERT INTO sources (kind, name, config_json, enabled, interval_seconds) "
            "VALUES (?, ?, ?, 1, ?)",
            (spec["kind"], spec["name"], json.dumps(spec["config"]), spec["interval_seconds"]),
        )
    conn.commit()


def _naive_utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _is_due(source_row: sqlite3.Row, now: datetime) -> bool:
    if not source_row["enabled"]:
        return False
    last_fetch_at = source_row["last_fetch_at"]
    if not last_fetch_at:
        return True
    last_dt = datetime.strptime(last_fetch_at, "%Y-%m-%d %H:%M:%S")
    return (now - last_dt).total_seconds() >= source_row["interval_seconds"]


def find_due_sources(conn: sqlite3.Connection, now: datetime | None = None) -> list[sqlite3.Row]:
    now = now or _naive_utc_now()
    rows = conn.execute("SELECT * FROM sources ORDER BY id").fetchall()
    return [row for row in rows if _is_due(row, now)]


def _persist_state(conn: sqlite3.Connection, source_id: int, content_hash: str) -> None:
    conn.execute(
        "INSERT INTO source_state (source_id, content_hash, updated_at) "
        "VALUES (?, ?, datetime('now')) "
        "ON CONFLICT (source_id) DO UPDATE SET "
        "content_hash = excluded.content_hash, updated_at = excluded.updated_at",
        (source_id, content_hash),
    )


def _record_fetch(
    conn: sqlite3.Connection,
    source_id: int,
    *,
    ok: bool,
    error: str | None,
    raw_count: int,
    created_count: int,
) -> None:
    if ok:
        conn.execute(
            "UPDATE sources SET last_fetch_at = datetime('now'), "
            "last_success_at = datetime('now'), last_error = NULL WHERE id = ?",
            (source_id,),
        )
    else:
        conn.execute(
            "UPDATE sources SET last_fetch_at = datetime('now'), last_error = ? WHERE id = ?",
            (error, source_id),
        )
    conn.execute(
        "INSERT INTO events (kind, payload_json) VALUES ('source_fetch', ?)",
        (
            json.dumps(
                {
                    "source_id": source_id,
                    "ok": ok,
                    "error": error,
                    "raw_count": raw_count,
                    "created_count": created_count,
                }
            ),
        ),
    )
    conn.commit()


def run_source(conn: sqlite3.Connection, vamp_config: Config, source_row: sqlite3.Row) -> dict:
    """Fetch one source and ingest its leads. Never raises — any adapter
    failure (network, bad config, policy refusal) is caught, recorded on
    this source's row, and returned in the stats dict instead."""
    source_id = source_row["id"]
    name = source_row["name"]
    try:
        adapter = build_adapter(vamp_config, conn, source_row)
        raw_leads = adapter.fetch()
    except Exception as exc:  # noqa: BLE001 - isolating one adapter's failure by design
        error = str(exc) or exc.__class__.__name__
        _record_fetch(conn, source_id, ok=False, error=error, raw_count=0, created_count=0)
        return {
            "source_id": source_id,
            "name": name,
            "ok": False,
            "error": error,
            "raw_count": 0,
            "created_count": 0,
        }

    created_count = 0
    for raw_lead in raw_leads:
        _lead_id, created, _existing = leads_service.create_lead(
            conn, raw_lead, source_id=source_id
        )
        if created:
            created_count += 1

    state_to_persist = getattr(adapter, "state_to_persist", None)
    if state_to_persist is not None:
        _persist_state(conn, source_id, state_to_persist)

    _record_fetch(
        conn, source_id, ok=True, error=None, raw_count=len(raw_leads), created_count=created_count
    )
    return {
        "source_id": source_id,
        "name": name,
        "ok": True,
        "error": None,
        "raw_count": len(raw_leads),
        "created_count": created_count,
    }


def run_due_sources(
    conn: sqlite3.Connection, vamp_config: Config, now: datetime | None = None
) -> list[dict]:
    return [run_source(conn, vamp_config, row) for row in find_due_sources(conn, now=now)]
