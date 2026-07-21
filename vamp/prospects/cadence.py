"""The cadence engine (PLAN.md §6): silence is not a no.

After Kaelyn sends a pitch (logged as a touch), the engine schedules the two
follow-ups the plan mandates (+7d, +21d) as ``reminders`` rows, respects a
per-prospect cooldown so no place is pestered too often, and the weekly
**Outreach Sprint** aggregation packages what's due into the one notification
that makes the whole thing a habit:

    "This week: 5 pitches drafted and ready, 3 follow-ups due. Open Vamp."

Every follow-up is still sent by a human — this only decides *when to remind
her*, never sends anything (CLAUDE.md hard rule: no auto-sending, ever).
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

# PLAN.md §6: "the cadence engine schedules the follow-ups (+7d, +21d)".
FOLLOW_UP_OFFSET_DAYS: tuple[int, ...] = (7, 21)

# Per-prospect cooldown fallback when prospects.cooldown_days is NULL
# (PLAN.md §13 "per-prospect cooldowns" — outreach never feels spammy).
DEFAULT_COOLDOWN_DAYS = 14

# reminders.ref_kind value for a scheduled prospect follow-up.
FOLLOW_UP_REF_KIND = "prospect_follow_up"

_TS_FMT = "%Y-%m-%d %H:%M:%S"


def naive_utc_now() -> datetime:
    """Match the ``datetime('now')`` SQLite default: naive UTC."""
    return datetime.now(UTC).replace(tzinfo=None)


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    # Reminders/touches are written naive-UTC; tolerate a trailing fractional
    # part or 'T' separator just in case a value arrives from elsewhere.
    text = value.strip().replace("T", " ")
    text = text.split(".", 1)[0]
    try:
        return datetime.strptime(text, _TS_FMT)
    except ValueError:
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            return None


def cooldown_days_for(prospect: sqlite3.Row | dict) -> int:
    value = prospect["cooldown_days"] if "cooldown_days" in prospect.keys() else None
    return value if value is not None else DEFAULT_COOLDOWN_DAYS


def in_cooldown(prospect: sqlite3.Row | dict, now: datetime | None = None) -> bool:
    """True when this prospect was touched too recently to pitch again."""
    now = now or naive_utc_now()
    last_touch = _parse_ts(prospect["last_touch_at"])
    if last_touch is None:
        return False
    return now < last_touch + timedelta(days=cooldown_days_for(prospect))


def cancel_follow_ups(conn: sqlite3.Connection, prospect_id: int) -> None:
    """Mark any outstanding follow-up reminders done — used when a prospect
    reaches a terminal state (booked/recurring/dead) so the sprint stops
    nagging about a conversation that's already resolved."""
    conn.execute(
        "UPDATE reminders SET done = 1 WHERE ref_kind = ? AND ref_id = ? AND done = 0",
        (FOLLOW_UP_REF_KIND, prospect_id),
    )


def schedule_follow_ups(
    conn: sqlite3.Connection,
    prospect_id: int,
    prospect_name: str,
    from_time: datetime | None = None,
) -> list[str]:
    """Replace this prospect's pending follow-up reminders with a fresh +7d/
    +21d pair anchored at ``from_time`` (the moment of the latest touch), and
    point ``prospects.next_touch_at`` at the soonest one.

    Returns the due dates scheduled (ISO), for logging/tests.
    """
    from_time = from_time or naive_utc_now()
    # A new touch supersedes older pending follow-ups (she re-engaged, so the
    # clock restarts) — clear them before scheduling the new pair.
    cancel_follow_ups(conn, prospect_id)

    due_dates: list[str] = []
    for i, offset in enumerate(FOLLOW_UP_OFFSET_DAYS, start=1):
        due = from_time + timedelta(days=offset)
        due_str = due.strftime(_TS_FMT)
        conn.execute(
            "INSERT INTO reminders (ref_kind, ref_id, due_at, message, done) "
            "VALUES (?, ?, ?, ?, 0)",
            (
                FOLLOW_UP_REF_KIND,
                prospect_id,
                due_str,
                f"Follow-up {i} due for {prospect_name} (no reply is not a no)",
            ),
        )
        due_dates.append(due_str)

    earliest = min(due_dates)
    conn.execute("UPDATE prospects SET next_touch_at = ? WHERE id = ?", (earliest, prospect_id))
    return due_dates


def due_follow_ups(conn: sqlite3.Connection, now: datetime | None = None) -> list[sqlite3.Row]:
    """Pending follow-up reminders whose due date has arrived, newest-due
    first, joined to the prospect so the sprint can name it."""
    now = now or naive_utc_now()
    return conn.execute(
        """
        SELECT r.id AS reminder_id, r.due_at, r.message,
               p.id AS prospect_id, p.name, p.category, p.area, p.status,
               p.angle, p.email, p.phone, p.website
        FROM reminders r
        JOIN prospects p ON p.id = r.ref_id
        WHERE r.ref_kind = ? AND r.done = 0 AND r.due_at <= ?
        ORDER BY r.due_at ASC
        """,
        (FOLLOW_UP_REF_KIND, now.strftime(_TS_FMT)),
    ).fetchall()


def outreach_sprint(conn: sqlite3.Connection, now: datetime | None = None) -> dict:
    """Weekly Outreach Sprint aggregation (PLAN.md §6/§7).

    Bundles the two things Kaelyn acts on each Sunday: pitches already drafted
    and ready to personalize-and-send, and follow-ups that have come due. The
    return value is what the sprint page and (in M7) the notification render.
    """
    now = now or naive_utc_now()

    pitches_ready = conn.execute(
        """
        SELECT id, name, category, area, angle, email, phone, website
        FROM prospects
        WHERE status = 'pitch_drafted'
        ORDER BY COALESCE(next_touch_at, '9999'), name COLLATE NOCASE
        """
    ).fetchall()

    follow_ups = due_follow_ups(conn, now=now)

    # Prospects researched and waiting for a pitch to be drafted — the top of
    # the funnel, surfaced so the pipeline never silently dries up.
    to_draft = conn.execute(
        """
        SELECT id, name, category, area, angle
        FROM prospects
        WHERE status = 'researched'
        ORDER BY name COLLATE NOCASE
        """
    ).fetchall()

    return {
        "generated_at": now.strftime(_TS_FMT),
        "pitches_ready": pitches_ready,
        "follow_ups_due": follow_ups,
        "to_draft": to_draft,
        "summary": {
            "pitches_ready": len(pitches_ready),
            "follow_ups_due": len(follow_ups),
            "to_draft": len(to_draft),
        },
    }


def sprint_headline(sprint: dict) -> str:
    """The one-line notification text (PLAN.md §6/§7)."""
    s = sprint["summary"]
    parts = []
    if s["pitches_ready"]:
        parts.append(f"{s['pitches_ready']} pitches drafted and ready")
    if s["follow_ups_due"]:
        parts.append(f"{s['follow_ups_due']} follow-ups due")
    if s["to_draft"]:
        parts.append(f"{s['to_draft']} to research into pitches")
    if not parts:
        return "No outreach due this week — the pipeline is quiet."
    return "This week: " + ", ".join(parts) + ". Open Vamp."
