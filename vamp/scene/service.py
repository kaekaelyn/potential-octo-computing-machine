"""Scene event CRUD, going flags, and the recap-reminder sync (PLAN.md §7).

``sync_recap_reminders`` is the catch-up-on-open shape from M2's source
polling applied here: called on every ``/scene`` page load, it walks the
"going" events, and for any whose most recent occurrence has passed since
the last time it asked, creates a single "met anyone?" reminder — guarded
by ``last_recap_at`` so repeat visits before the next occurrence never
duplicate it.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date

from vamp.scene import cadence as cadence_engine

# reminders.ref_kind value for a scheduled post-event recap prompt.
RECAP_REF_KIND = "scene_recap"

_EDITABLE_COLUMNS: tuple[str, ...] = ("name", "venue", "area", "url", "kind", "notes", "playbook")


def list_events(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM scene_events ORDER BY name COLLATE NOCASE").fetchall()


def get_event(conn: sqlite3.Connection, event_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM scene_events WHERE id = ?", (event_id,)).fetchone()


def create_event(conn: sqlite3.Connection, fields: dict, cadence: dict | None) -> int:
    cols = list(_EDITABLE_COLUMNS) + ["cadence_json", "going"]
    placeholders = ", ".join("?" for _ in cols)
    params = [fields.get(c) for c in _EDITABLE_COLUMNS] + [
        json.dumps(cadence) if cadence else None,
        0,
    ]
    cur = conn.execute(
        f"INSERT INTO scene_events ({', '.join(cols)}) VALUES ({placeholders})", params
    )
    conn.commit()
    return cur.lastrowid


def update_event(
    conn: sqlite3.Connection, event_id: int, fields: dict, cadence: dict | None
) -> None:
    assignments = ", ".join(f"{c} = ?" for c in _EDITABLE_COLUMNS)
    params = [fields.get(c) for c in _EDITABLE_COLUMNS] + [
        json.dumps(cadence) if cadence else None,
        event_id,
    ]
    conn.execute(f"UPDATE scene_events SET {assignments}, cadence_json = ? WHERE id = ?", params)
    conn.commit()


def delete_event(conn: sqlite3.Connection, event_id: int) -> None:
    conn.execute(
        "UPDATE reminders SET done = 1 WHERE ref_kind = ? AND ref_id = ?",
        (RECAP_REF_KIND, event_id),
    )
    conn.execute("DELETE FROM scene_events WHERE id = ?", (event_id,))
    conn.commit()


def toggle_going(conn: sqlite3.Connection, event_id: int) -> None:
    conn.execute("UPDATE scene_events SET going = 1 - going WHERE id = ?", (event_id,))
    conn.commit()


def sync_recap_reminders(conn: sqlite3.Connection, today: date | None = None) -> int:
    today = today or date.today()
    created = 0
    for row in conn.execute("SELECT * FROM scene_events WHERE going = 1").fetchall():
        cadence = json.loads(row["cadence_json"]) if row["cadence_json"] else None
        occurred = cadence_engine.previous_occurrence(cadence, today)
        if occurred is None:
            continue
        last_recap = row["last_recap_at"]
        if last_recap and occurred.isoformat() <= last_recap:
            continue
        conn.execute(
            "INSERT INTO reminders (ref_kind, ref_id, due_at, message, done) "
            "VALUES (?, ?, ?, ?, 0)",
            (
                RECAP_REF_KIND,
                row["id"],
                occurred.strftime("%Y-%m-%d %H:%M:%S"),
                f"Met anyone at {row['name']}? ({occurred.isoformat()})",
            ),
        )
        conn.execute(
            "UPDATE scene_events SET last_recap_at = ? WHERE id = ?",
            (occurred.isoformat(), row["id"]),
        )
        created += 1
    conn.commit()
    return created


def open_recap_reminder(conn: sqlite3.Connection, event_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM reminders WHERE ref_kind = ? AND ref_id = ? AND done = 0 "
        "ORDER BY due_at DESC LIMIT 1",
        (RECAP_REF_KIND, event_id),
    ).fetchone()


def dismiss_recap(conn: sqlite3.Connection, event_id: int) -> None:
    conn.execute(
        "UPDATE reminders SET done = 1 WHERE ref_kind = ? AND ref_id = ? AND done = 0",
        (RECAP_REF_KIND, event_id),
    )
    conn.commit()
