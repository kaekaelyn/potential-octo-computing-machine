"""Gig lifecycle (PLAN.md §8/§12 M6): offered → confirmed → played → paid.

Reaching ``played`` arms a chase-unpaid reminder at +14 days, the same
schedule-then-cancel-if-resolved shape as the prospects cadence engine
(``vamp/prospects/cadence.py``) — the reminder fires only if the gig is
still unpaid when it comes due; reaching ``paid`` cancels it outright.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

GIG_STATES: tuple[str, ...] = ("offered", "confirmed", "played", "paid")

STATE_LABELS: dict[str, str] = {
    "offered": "Offered",
    "confirmed": "Confirmed",
    "played": "Played",
    "paid": "Paid",
}

# reminders.ref_kind value for a scheduled chase-unpaid reminder.
CHASE_UNPAID_REF_KIND = "gig_chase_unpaid"

# PLAN.md §8: "a 'chase unpaid' reminder if a gig stays played-not-paid past 14 days".
CHASE_UNPAID_OFFSET_DAYS = 14

_TS_FMT = "%Y-%m-%d %H:%M:%S"

_EDITABLE_COLUMNS: tuple[str, ...] = (
    "prospect_id",
    "lead_id",
    "date",
    "venue",
    "pay_agreed",
    "pay_received",
    "expenses",
    "mileage",
    "notes",
)


def naive_utc_now() -> datetime:
    """Match the ``datetime('now')`` SQLite default: naive UTC."""
    return datetime.now(UTC).replace(tzinfo=None)


def next_state(current: str) -> str | None:
    """The state the 'advance' button moves to, or None at the end of the
    chain (marking paid, or correcting a mistake, is always explicit)."""
    if current not in GIG_STATES:
        return None
    idx = GIG_STATES.index(current)
    if idx + 1 >= len(GIG_STATES):
        return None
    return GIG_STATES[idx + 1]


def _gig_label(gig: sqlite3.Row) -> str:
    venue = gig["venue"] or "gig"
    date = gig["date"] or "date TBD"
    return f"{venue} ({date})"


def _normalize_fields(fields: dict) -> dict:
    values = {k: fields.get(k) for k in _EDITABLE_COLUMNS}
    for numeric in ("pay_agreed", "pay_received", "expenses", "mileage"):
        v = values.get(numeric)
        values[numeric] = float(v) if v not in (None, "") else None
    for fk in ("prospect_id", "lead_id"):
        v = values.get(fk)
        values[fk] = int(v) if v not in (None, "") else None
    return values


def list_gigs(conn: sqlite3.Connection, *, state: str | None = None) -> list[sqlite3.Row]:
    if state:
        return conn.execute(
            "SELECT * FROM gigs WHERE state = ? ORDER BY date DESC, id DESC", (state,)
        ).fetchall()
    return conn.execute("SELECT * FROM gigs ORDER BY date DESC, id DESC").fetchall()


def get_gig(conn: sqlite3.Connection, gig_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM gigs WHERE id = ?", (gig_id,)).fetchone()


def create_gig(conn: sqlite3.Connection, fields: dict) -> int:
    values = _normalize_fields(fields)
    strategic = 1 if fields.get("strategic") else 0
    cols = list(_EDITABLE_COLUMNS) + ["state", "strategic"]
    placeholders = ", ".join("?" for _ in cols)
    params = [values[c] for c in _EDITABLE_COLUMNS] + ["offered", strategic]
    cur = conn.execute(f"INSERT INTO gigs ({', '.join(cols)}) VALUES ({placeholders})", params)
    conn.commit()
    return cur.lastrowid


def update_gig(conn: sqlite3.Connection, gig_id: int, fields: dict) -> None:
    values = _normalize_fields(fields)
    strategic = 1 if fields.get("strategic") else 0
    assignments = ", ".join(f"{c} = ?" for c in _EDITABLE_COLUMNS)
    params = [values[c] for c in _EDITABLE_COLUMNS] + [strategic, gig_id]
    conn.execute(f"UPDATE gigs SET {assignments}, strategic = ? WHERE id = ?", params)
    conn.commit()


def delete_gig(conn: sqlite3.Connection, gig_id: int) -> None:
    conn.execute("DELETE FROM invoices WHERE gig_id = ?", (gig_id,))
    conn.execute("DELETE FROM referrals WHERE gig_id = ?", (gig_id,))
    conn.execute(
        "UPDATE reminders SET done = 1 WHERE ref_kind = ? AND ref_id = ?",
        (CHASE_UNPAID_REF_KIND, gig_id),
    )
    conn.execute("DELETE FROM gigs WHERE id = ?", (gig_id,))
    conn.commit()


def cancel_chase_unpaid(conn: sqlite3.Connection, gig_id: int) -> None:
    conn.execute(
        "UPDATE reminders SET done = 1 WHERE ref_kind = ? AND ref_id = ? AND done = 0",
        (CHASE_UNPAID_REF_KIND, gig_id),
    )


def schedule_chase_unpaid(
    conn: sqlite3.Connection, gig: sqlite3.Row, from_time: datetime | None = None
) -> str:
    """(Re)schedule this gig's chase-unpaid reminder for +14 days from
    ``from_time`` (the moment it was marked played). Returns the due date."""
    from_time = from_time or naive_utc_now()
    cancel_chase_unpaid(conn, gig["id"])
    due = from_time + timedelta(days=CHASE_UNPAID_OFFSET_DAYS)
    due_str = due.strftime(_TS_FMT)
    conn.execute(
        "INSERT INTO reminders (ref_kind, ref_id, due_at, message, done) VALUES (?, ?, ?, ?, 0)",
        (CHASE_UNPAID_REF_KIND, gig["id"], due_str, f"Chase unpaid: {_gig_label(gig)}"),
    )
    return due_str


def set_state(
    conn: sqlite3.Connection, gig_id: int, new_state: str, now: datetime | None = None
) -> None:
    if new_state not in GIG_STATES:
        raise ValueError(f"unknown gig state: {new_state!r}")
    gig = get_gig(conn, gig_id)
    if gig is None:
        raise ValueError(f"no gig {gig_id}")
    now = now or naive_utc_now()
    now_str = now.strftime(_TS_FMT)

    updates: dict[str, str] = {"state": new_state}
    if new_state == "played" and not gig["played_at"]:
        updates["played_at"] = now_str
    if new_state == "paid" and not gig["paid_at"]:
        updates["paid_at"] = now_str

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    conn.execute(f"UPDATE gigs SET {set_clause} WHERE id = ?", (*updates.values(), gig_id))

    if new_state == "played":
        schedule_chase_unpaid(conn, get_gig(conn, gig_id), from_time=now)
    elif new_state == "paid":
        cancel_chase_unpaid(conn, gig_id)

    conn.commit()


def advance_state(conn: sqlite3.Connection, gig_id: int) -> str | None:
    gig = get_gig(conn, gig_id)
    if gig is None:
        return None
    nxt = next_state(gig["state"])
    if nxt is None:
        return None
    set_state(conn, gig_id, nxt)
    return nxt


def due_chase_reminders(conn: sqlite3.Connection, now: datetime | None = None) -> list[sqlite3.Row]:
    """Chase-unpaid reminders that have come due, joined to their gig —
    used by the consolidated reminders page."""
    now = now or naive_utc_now()
    return conn.execute(
        """
        SELECT r.id AS reminder_id, r.due_at, r.message,
               g.id AS gig_id, g.venue, g.date, g.pay_agreed, g.pay_received, g.state
        FROM reminders r
        JOIN gigs g ON g.id = r.ref_id
        WHERE r.ref_kind = ? AND r.done = 0 AND r.due_at <= ?
        ORDER BY r.due_at ASC
        """,
        (CHASE_UNPAID_REF_KIND, now.strftime(_TS_FMT)),
    ).fetchall()
