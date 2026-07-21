"""Sends the morning digest and Sunday Outreach Sprint as real notifications
(PLAN.md §7/§9/§12 M7). Both the scheduled cron jobs (``vamp.notify.scheduler``)
and the manual "send now" buttons on ``/notify`` funnel through here, so
there is exactly one place that decides "has this already gone out today/
this week" — guarded via the ``events`` table (one row per kind+period,
mirroring how ``vamp.ai.batch`` logs a summary row per nightly run) so a
misfire-grace catch-up run and a manual demo send can't double-notify.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from vamp.config import Config
from vamp.notify import termux
from vamp.notify.digest import digest_headline, morning_digest
from vamp.playbooks.activation import sync_activation_reminders
from vamp.prospects import cadence as prospect_cadence
from vamp.prospects.cadence import naive_utc_now

MORNING_DIGEST_KIND = "morning_digest_sent"
SPRINT_KIND = "sprint_notification_sent"

MORNING_DIGEST_NOTIFICATION_ID = "vamp-morning-digest"
SPRINT_NOTIFICATION_ID = "vamp-outreach-sprint"


def _event_kind(kind: str, key: str) -> str:
    return f"{kind}:{key}"


def _already_sent(conn: sqlite3.Connection, kind: str, key: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM events WHERE kind = ? LIMIT 1", (_event_kind(kind, key),)
        ).fetchone()
        is not None
    )


def _record_sent(conn: sqlite3.Connection, kind: str, key: str, payload: dict) -> None:
    conn.execute(
        "INSERT INTO events (kind, payload_json) VALUES (?, ?)",
        (_event_kind(kind, key), json.dumps(payload)),
    )
    conn.commit()


def send_morning_digest(
    conn: sqlite3.Connection, config: Config, *, now: datetime | None = None, force: bool = False
) -> dict:
    """Compose + send the morning digest, unless one already went out today.
    ``force=True`` (the manual "send now" button) bypasses that guard so the
    milestone can be demoed without waiting for the next calendar day."""
    now = now or naive_utc_now()
    date_key = now.strftime("%Y-%m-%d")
    if not force and _already_sent(conn, MORNING_DIGEST_KIND, date_key):
        return {"skipped": True, "reason": "already sent today"}

    activated = sync_activation_reminders(conn, today=now.date())
    digest = morning_digest(conn, now=now)
    headline = digest_headline(digest)
    body = headline
    if activated:
        plural = "s" if activated != 1 else ""
        body += f" {activated} playbook{plural} activated this month — see /playbooks."

    result = termux.send_notification(
        "Vamp — morning digest", body, notification_id=MORNING_DIGEST_NOTIFICATION_ID
    )
    _record_sent(
        conn,
        MORNING_DIGEST_KIND,
        date_key,
        {
            "headline": body,
            "notify_status": result.status,
            "notify_detail": result.detail,
            "summary": digest["summary"],
            "playbooks_activated": activated,
        },
    )
    return {"skipped": False, "headline": body, "notify": result, "digest": digest}


def send_sunday_sprint(
    conn: sqlite3.Connection, config: Config, *, now: datetime | None = None, force: bool = False
) -> dict:
    """Compose + send the weekly Outreach Sprint, unless one already went
    out this ISO week."""
    now = now or naive_utc_now()
    week_key = now.strftime("%G-W%V")
    if not force and _already_sent(conn, SPRINT_KIND, week_key):
        return {"skipped": True, "reason": "already sent this week"}

    sprint = prospect_cadence.outreach_sprint(conn, now=now)
    headline = prospect_cadence.sprint_headline(sprint)

    result = termux.send_notification(
        "Vamp — Outreach Sprint", headline, notification_id=SPRINT_NOTIFICATION_ID
    )
    _record_sent(
        conn,
        SPRINT_KIND,
        week_key,
        {
            "headline": headline,
            "notify_status": result.status,
            "notify_detail": result.detail,
            "summary": sprint["summary"],
        },
    )
    return {"skipped": False, "headline": headline, "notify": result, "sprint": sprint}
