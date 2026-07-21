"""Seasonal playbook activation reminders (PLAN.md §6: "Playbooks activate
as reminders on schedule"; §12 M7). Shares the ``active_months`` parsing
with the playbook list page (which flags a playbook "active now") and, once
a month, drops a reminder onto the consolidated ``/reminders`` page for
every playbook whose ``active_months`` includes the current month — the
same sync-on-read, guard-against-duplicates shape as the M6 scene recap
reminders (``vamp/scene/service.py``).
"""

from __future__ import annotations

import sqlite3
from datetime import date

# reminders.ref_kind value for a scheduled playbook activation reminder.
PLAYBOOK_ACTIVATION_REF_KIND = "playbook_activation"


def active_months_list(active_months: str | None) -> list[int]:
    """Parse the ``playbooks.active_months`` comma-separated column
    (e.g. "9,12,1") into a list of month numbers."""
    if not active_months:
        return []
    out = []
    for part in active_months.split(","):
        part = part.strip()
        if part.isdigit():
            out.append(int(part))
    return out


def sync_activation_reminders(conn: sqlite3.Connection, today: date | None = None) -> int:
    """Ensure every playbook active this calendar month has an open
    reminder — at most one per playbook per month, guarded by checking for
    an existing reminder whose ``due_at`` already falls in this year-month."""
    today = today or date.today()
    year_month = today.strftime("%Y-%m")
    created = 0
    for row in conn.execute("SELECT * FROM playbooks").fetchall():
        months = active_months_list(row["active_months"])
        if today.month not in months:
            continue
        exists = conn.execute(
            "SELECT 1 FROM reminders WHERE ref_kind = ? AND ref_id = ? AND due_at LIKE ?",
            (PLAYBOOK_ACTIVATION_REF_KIND, row["id"], f"{year_month}%"),
        ).fetchone()
        if exists:
            continue
        conn.execute(
            "INSERT INTO reminders (ref_kind, ref_id, due_at, message, done) "
            "VALUES (?, ?, ?, ?, 0)",
            (
                PLAYBOOK_ACTIVATION_REF_KIND,
                row["id"],
                f"{year_month}-01 00:00:00",
                f"{row['title']} is active this month — see the playbook for what to run.",
            ),
        )
        created += 1
    conn.commit()
    return created
