"""Caches the last ``check_claude_health`` result in the ``profile`` table
so the health panel doesn't shell out to the CLI on every page view — only
when the user taps "Check now" (or a batch run refreshes it as a side
effect)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from vamp.ai.health import HealthStatus, check_claude_health

_KEY_STATUS = "ai_health_status"
_KEY_DETAIL = "ai_health_detail"
_KEY_CHECKED_AT = "ai_health_checked_at"


def _set(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO profile (key, value) VALUES (?, ?) "
        "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def get_cached_health(conn: sqlite3.Connection) -> tuple[HealthStatus | None, str | None]:
    """Returns ``(status, checked_at)`` — ``(None, None)`` if never checked."""
    rows = {
        r["key"]: r["value"]
        for r in conn.execute(
            "SELECT key, value FROM profile WHERE key IN (?, ?, ?)",
            (_KEY_STATUS, _KEY_DETAIL, _KEY_CHECKED_AT),
        )
    }
    if _KEY_STATUS not in rows:
        return None, None
    return HealthStatus(status=rows[_KEY_STATUS], detail=rows.get(_KEY_DETAIL, "")), rows.get(
        _KEY_CHECKED_AT
    )


def refresh_health(
    conn: sqlite3.Connection, *, binary: str = "claude", timeout_seconds: int = 30
) -> HealthStatus:
    """Run a fresh check and persist it. Never raises — ``check_claude_health``
    already normalizes every failure into a ``HealthStatus``."""
    status = check_claude_health(binary=binary, timeout_seconds=timeout_seconds)
    checked_at = datetime.now(UTC).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")
    _set(conn, _KEY_STATUS, status.status)
    _set(conn, _KEY_DETAIL, status.detail)
    _set(conn, _KEY_CHECKED_AT, checked_at)
    conn.commit()
    return status
