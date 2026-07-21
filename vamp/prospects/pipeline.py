"""The prospects pipeline (PLAN.md §6): states, the per-prospect angle, the
touches log, and status transitions — with the cadence engine wired in so
logging a pitch automatically schedules its follow-ups.

    identified → researched → pitch_drafted → contacted →
    follow_up_1 → follow_up_2 → in_conversation → booked → recurring | dead

Nothing here sends a message; a touch is Kaelyn recording something she
already did by hand (CLAUDE.md: a human sends every single one).
"""

from __future__ import annotations

import json
import sqlite3

from vamp.prospects import cadence

# Ordered pipeline (PLAN.md §6). ``recurring`` and ``dead`` are terminal.
PIPELINE_STATES: tuple[str, ...] = (
    "identified",
    "researched",
    "pitch_drafted",
    "contacted",
    "follow_up_1",
    "follow_up_2",
    "in_conversation",
    "booked",
    "recurring",
    "dead",
)

TERMINAL_STATES: frozenset[str] = frozenset({"recurring", "dead"})

# States after which a touch should arm the +7d/+21d follow-up clock: she has
# reached out and is now waiting on a reply.
AWAITING_REPLY_STATES: frozenset[str] = frozenset({"contacted", "follow_up_1", "follow_up_2"})

STATE_LABELS: dict[str, str] = {
    "identified": "Identified",
    "researched": "Researched",
    "pitch_drafted": "Pitch drafted",
    "contacted": "Contacted",
    "follow_up_1": "Follow-up 1 sent",
    "follow_up_2": "Follow-up 2 sent",
    "in_conversation": "In conversation",
    "booked": "Booked",
    "recurring": "Recurring",
    "dead": "Dead",
}

# Editable prospect columns (everything a human curates — never the derived
# last_touch_at/next_touch_at, which the cadence engine owns).
_EDITABLE_COLUMNS: tuple[str, ...] = (
    "name",
    "category",
    "area",
    "address",
    "phone",
    "email",
    "website",
    "has_piano",
    "angle",
    "source",
    "verified",
    "notes",
    "cooldown_days",
    "playbook",
)


def next_state(current: str) -> str | None:
    """The state the 'advance' button moves to, or None at the end of the
    non-terminal chain (from ``booked`` the human picks recurring vs dead)."""
    if current not in PIPELINE_STATES:
        return None
    idx = PIPELINE_STATES.index(current)
    if current in TERMINAL_STATES or current == "booked":
        return None
    return PIPELINE_STATES[idx + 1]


def _record_event(conn: sqlite3.Connection, kind: str, payload: dict) -> None:
    conn.execute(
        "INSERT INTO events (kind, payload_json) VALUES (?, ?)",
        (kind, json.dumps(payload)),
    )


def list_prospects(
    conn: sqlite3.Connection,
    *,
    status: str | None = None,
    category: str | None = None,
    playbook: str | None = None,
) -> list[sqlite3.Row]:
    clauses = []
    params: list = []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if category:
        clauses.append("category = ?")
        params.append(category)
    if playbook:
        clauses.append("playbook = ?")
        params.append(playbook)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return conn.execute(
        f"SELECT * FROM prospects {where} "
        "ORDER BY (status IN ('recurring','dead')), name COLLATE NOCASE",
        params,
    ).fetchall()


def get_prospect(conn: sqlite3.Connection, prospect_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM prospects WHERE id = ?", (prospect_id,)).fetchone()


def prospect_touches(conn: sqlite3.Connection, prospect_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM touches WHERE prospect_id = ? ORDER BY ts DESC, id DESC",
        (prospect_id,),
    ).fetchall()


def category_counts(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT category, COUNT(*) AS n FROM prospects "
        "GROUP BY category ORDER BY category COLLATE NOCASE"
    ).fetchall()


def _normalize_fields(fields: dict) -> dict:
    values = {k: fields.get(k) for k in _EDITABLE_COLUMNS}
    # Booleans/ints arrive from forms as checkbox/str; store 0/1/None.
    for flag in ("has_piano", "verified"):
        v = values.get(flag)
        if v is None or v == "":
            values[flag] = None if flag == "has_piano" else 0
        else:
            values[flag] = int(bool(int(v)) if str(v).isdigit() else bool(v))
    cd = values.get("cooldown_days")
    values["cooldown_days"] = int(cd) if cd not in (None, "") else None
    return values


def create_prospect(conn: sqlite3.Connection, fields: dict) -> int:
    values = _normalize_fields(fields)
    status = fields.get("status") or "identified"
    if status not in PIPELINE_STATES:
        status = "identified"
    socials = fields.get("socials_json")
    cols = list(_EDITABLE_COLUMNS) + ["status", "socials_json"]
    placeholders = ", ".join("?" for _ in cols)
    params = [values[c] for c in _EDITABLE_COLUMNS] + [status, socials]
    cur = conn.execute(
        f"INSERT INTO prospects ({', '.join(cols)}) VALUES ({placeholders})",
        params,
    )
    conn.commit()
    prospect_id = cur.lastrowid
    _record_event(conn, "prospect_created", {"prospect_id": prospect_id, "name": values["name"]})
    conn.commit()
    return prospect_id


def update_prospect(conn: sqlite3.Connection, prospect_id: int, fields: dict) -> None:
    values = _normalize_fields(fields)
    assignments = ", ".join(f"{c} = ?" for c in _EDITABLE_COLUMNS)
    params = [values[c] for c in _EDITABLE_COLUMNS] + [prospect_id]
    conn.execute(f"UPDATE prospects SET {assignments} WHERE id = ?", params)
    conn.commit()


def set_status(conn: sqlite3.Connection, prospect_id: int, new_status: str) -> None:
    if new_status not in PIPELINE_STATES:
        raise ValueError(f"unknown prospect status: {new_status!r}")
    conn.execute("UPDATE prospects SET status = ? WHERE id = ?", (new_status, prospect_id))
    if new_status in TERMINAL_STATES:
        # Conversation resolved — stop the follow-up nagging.
        cadence.cancel_follow_ups(conn, prospect_id)
        conn.execute("UPDATE prospects SET next_touch_at = NULL WHERE id = ?", (prospect_id,))
    _record_event(conn, "prospect_status", {"prospect_id": prospect_id, "status": new_status})
    conn.commit()


def advance_status(conn: sqlite3.Connection, prospect_id: int) -> str | None:
    row = get_prospect(conn, prospect_id)
    if row is None:
        return None
    nxt = next_state(row["status"])
    if nxt is None:
        return None
    set_status(conn, prospect_id, nxt)
    return nxt


def log_touch(
    conn: sqlite3.Connection,
    prospect_id: int,
    *,
    channel: str | None,
    summary: str | None,
    outcome: str | None,
    schedule_follow_ups: bool = True,
) -> int:
    """Record something Kaelyn already did (a pitch, a call, a reply received)
    and, unless the prospect is terminal, (re)arm the +7d/+21d follow-up clock.

    ``schedule_follow_ups=False`` logs a bare note (e.g. an inbound reply)
    without touching the cadence.
    """
    row = get_prospect(conn, prospect_id)
    if row is None:
        raise ValueError(f"no prospect {prospect_id}")

    now = cadence.naive_utc_now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.execute(
        "INSERT INTO touches (prospect_id, ts, channel, summary, outcome) VALUES (?, ?, ?, ?, ?)",
        (prospect_id, now_str, channel, summary, outcome),
    )
    conn.execute("UPDATE prospects SET last_touch_at = ? WHERE id = ?", (now_str, prospect_id))

    if schedule_follow_ups and row["status"] not in TERMINAL_STATES:
        cadence.schedule_follow_ups(conn, prospect_id, row["name"], from_time=now)

    _record_event(
        conn,
        "prospect_touch",
        {"prospect_id": prospect_id, "channel": channel, "outcome": outcome},
    )
    conn.commit()
    return cur.lastrowid


def delete_prospect(conn: sqlite3.Connection, prospect_id: int) -> None:
    conn.execute("DELETE FROM touches WHERE prospect_id = ?", (prospect_id,))
    conn.execute(
        "UPDATE reminders SET done = 1 WHERE ref_kind = ? AND ref_id = ?",
        (cadence.FOLLOW_UP_REF_KIND, prospect_id),
    )
    conn.execute("DELETE FROM prospects WHERE id = ?", (prospect_id,))
    conn.commit()
