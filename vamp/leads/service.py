"""Lead creation: dedupe + hard filters + insert, and the structural
Paying vs Stepping-stones shelf split (PLAN.md §4)."""

from __future__ import annotations

import json
import sqlite3

from vamp import dedupe
from vamp.capture.parser import ParsedLead
from vamp.filters import run_hard_filters

# Structural rule: unpaid never sorts into Paying. Only confirmed pay
# kinds count — tips/unknown/unpaid all land on Stepping-stones.
PAYING_KINDS = {"flat", "hourly", "salary"}


def is_paying(lead: sqlite3.Row) -> bool:
    return lead["pay_kind"] in PAYING_KINDS


def _capture_source_id(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT id FROM sources WHERE kind = 'capture'").fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        "INSERT INTO sources (kind, name, enabled) VALUES ('capture', 'Share/paste capture', 1)"
    )
    conn.commit()
    return cur.lastrowid


def create_lead(
    conn: sqlite3.Connection, parsed: ParsedLead, source_id: int | None = None
) -> tuple[int, bool, sqlite3.Row | None]:
    """Insert ``parsed`` as a new lead unless it's a duplicate.

    ``parsed`` may be a ``capture.parser.ParsedLead`` or any object with the
    same attributes — ``sources.base.RawLead`` (M2 adapters) included.
    ``source_id`` attributes it to a specific source row; omitted, it falls
    back to the shared capture-source row (M1 behavior).

    Returns ``(lead_id, created, existing_row)`` — ``created`` is False and
    ``existing_row`` is the prior lead when a dedupe key already matched.
    """
    url_h = dedupe.url_hash(parsed.url)
    fuzzy_h = dedupe.fuzzy_key(parsed.title, parsed.org, parsed.event_date)
    existing = dedupe.find_duplicate(conn, url_h, fuzzy_h)
    if existing:
        return existing["id"], False, existing

    combined_text = f"{parsed.title}\n{parsed.description}"
    reasons = run_hard_filters(combined_text)
    state = "excluded" if reasons else "inbox"
    excluded_reason = ",".join(reasons) if reasons else None
    source_id = source_id if source_id is not None else _capture_source_id(conn)

    cur = conn.execute(
        """
        INSERT INTO leads (
            source_id, kind, dedupe_hash, url_hash, url, title, org, location,
            pay_min, pay_max, pay_kind, deadline, event_date, posted_at, description,
            state, excluded_reason, needs_review, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source_id,
            parsed.kind,
            fuzzy_h,
            url_h,
            parsed.url,
            parsed.title,
            parsed.org,
            parsed.location,
            parsed.pay_min,
            parsed.pay_max,
            parsed.pay_kind,
            parsed.deadline,
            parsed.event_date,
            getattr(parsed, "posted_at", None),
            parsed.description,
            state,
            excluded_reason,
            int(parsed.needs_review),
            json.dumps(parsed.raw),
        ),
    )
    conn.commit()
    return cur.lastrowid, True, None


def restore_lead(conn: sqlite3.Connection, lead_id: int) -> None:
    conn.execute(
        "UPDATE leads SET state = 'inbox', excluded_reason = NULL WHERE id = ?", (lead_id,)
    )
    conn.commit()


def update_lead(conn: sqlite3.Connection, lead_id: int, fields: dict) -> None:
    """Finish-by-hand edit: overwrite the given fields, clear needs_review,
    and re-run the hard filters against the edited text."""
    columns = (
        "title",
        "org",
        "location",
        "url",
        "event_date",
        "deadline",
        "pay_kind",
        "pay_min",
        "pay_max",
        "description",
    )
    values = {k: fields.get(k) for k in columns}

    combined_text = f"{values['title'] or ''}\n{values['description'] or ''}"
    reasons = run_hard_filters(combined_text)
    state = "excluded" if reasons else "inbox"
    excluded_reason = ",".join(reasons) if reasons else None
    url_h = dedupe.url_hash(values["url"])
    fuzzy_h = dedupe.fuzzy_key(values["title"], values["org"], values["event_date"])

    conn.execute(
        """
        UPDATE leads SET
            title = ?, org = ?, location = ?, url = ?, event_date = ?, deadline = ?,
            pay_kind = ?, pay_min = ?, pay_max = ?, description = ?,
            state = ?, excluded_reason = ?, needs_review = 0,
            url_hash = ?, dedupe_hash = ?
        WHERE id = ?
        """,
        (
            values["title"],
            values["org"],
            values["location"],
            values["url"],
            values["event_date"],
            values["deadline"],
            values["pay_kind"],
            values["pay_min"] or None,
            values["pay_max"] or None,
            values["description"],
            state,
            excluded_reason,
            url_h,
            fuzzy_h,
            lead_id,
        ),
    )
    conn.commit()
