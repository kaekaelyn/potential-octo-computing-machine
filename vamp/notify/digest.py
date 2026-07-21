"""Composes the morning digest (PLAN.md §7): "2 new paying leads (1 READY),
3 follow-ups due, open mic tonight at [venue]." Pure read/compose functions
— no I/O beyond SELECTs, no sending. The Sunday Outreach Sprint has its own
composition already (``vamp.prospects.cadence.outreach_sprint`` /
``sprint_headline``, M4); ``vamp.notify.jobs`` is what actually sends either
one and guards against sending twice.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta

from vamp.gigs import pipeline as gigs_pipeline
from vamp.leads import service as leads_service
from vamp.prospects import cadence as prospect_cadence
from vamp.prospects.cadence import naive_utc_now
from vamp.scene import cadence as scene_cadence
from vamp.vault import matching as vault_matching

_TS_FMT = "%Y-%m-%d %H:%M:%S"

# The digest looks back a rolling 24h from whenever it's composed, rather
# than a calendar day, so it reads correctly regardless of what time the
# scheduled job (or a manual "send now") actually runs.
LOOKBACK_HOURS = 24


def _new_paying_leads(conn: sqlite3.Connection, window_start: datetime) -> list[sqlite3.Row]:
    rows = conn.execute(
        "SELECT * FROM leads WHERE state != 'excluded' AND first_seen_at >= ? "
        "ORDER BY first_seen_at DESC",
        (window_start.strftime(_TS_FMT),),
    ).fetchall()
    return [r for r in rows if leads_service.is_paying(r)]


def _tonight_events(conn: sqlite3.Connection, today) -> list[sqlite3.Row]:
    """ "Going" scene events whose next occurrence lands today (PLAN.md §7's
    "open mic tonight at [venue]")."""
    tonight = []
    for row in conn.execute("SELECT * FROM scene_events WHERE going = 1").fetchall():
        cadence = json.loads(row["cadence_json"]) if row["cadence_json"] else None
        if scene_cadence.next_occurrence(cadence, today=today) == today:
            tonight.append(row)
    return tonight


def morning_digest(conn: sqlite3.Connection, now: datetime | None = None) -> dict:
    now = now or naive_utc_now()
    today = now.date()
    window_start = now - timedelta(hours=LOOKBACK_HOURS)

    paying = _new_paying_leads(conn, window_start)
    statuses = vault_matching.status_for_leads(conn, [r["id"] for r in paying])
    ready_count = sum(1 for r in paying if statuses.get(r["id"], {}).get("ready"))

    follow_ups_due = prospect_cadence.due_follow_ups(conn, now=now)
    chase_unpaid_due = gigs_pipeline.due_chase_reminders(conn, now=now)
    tonight = _tonight_events(conn, today)

    return {
        "generated_at": now.strftime(_TS_FMT),
        "new_paying_leads": paying,
        "follow_ups_due": follow_ups_due,
        "chase_unpaid_due": chase_unpaid_due,
        "tonight_events": tonight,
        "summary": {
            "new_paying": len(paying),
            "new_paying_ready": ready_count,
            "follow_ups_due": len(follow_ups_due) + len(chase_unpaid_due),
            "tonight_events": len(tonight),
        },
    }


def digest_headline(digest: dict) -> str:
    """The one-line notification text (PLAN.md §7)."""
    s = digest["summary"]
    parts: list[str] = []

    if s["new_paying"]:
        lead_word = "lead" if s["new_paying"] == 1 else "leads"
        ready = f" ({s['new_paying_ready']} READY)" if s["new_paying_ready"] else ""
        parts.append(f"{s['new_paying']} new paying {lead_word}{ready}")

    if s["follow_ups_due"]:
        n = s["follow_ups_due"]
        parts.append(f"{n} follow-up{'s' if n != 1 else ''} due")

    for event in digest["tonight_events"]:
        label = event["name"]
        if event["venue"]:
            label += f" at {event['venue']}"
        parts.append(f"{label} tonight")

    if not parts:
        return "Quiet morning — nothing new. Open Vamp anyway."
    return ", ".join(parts) + "."
