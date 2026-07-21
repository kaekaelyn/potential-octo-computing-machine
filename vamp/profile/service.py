"""Bare key/value profile storage (``profile`` table, PLAN.md §10) — the
handful of fields AI drafting (pitches, bios, follow-ups) reads to sound
like her instead of a generic template: display name, instrument, home
area, and a free-text voice sample she pastes in once (a paragraph or two
of her own writing, so drafts can be asked to match it)."""

from __future__ import annotations

import sqlite3

FIELDS: tuple[str, ...] = (
    "display_name",
    "instrument",
    "home_area",
    "voice_sample",
    "rate_floor",
)

DEFAULTS: dict[str, str] = {
    "display_name": "Kaelyn",
    "instrument": "pianist/vocalist",
    "home_area": "the Oklahoma City metro",
    "voice_sample": "",
    # Empty = no floor set yet; PLAN.md §8's below-floor chips (M6) stay off
    # until she sets one from researched rates on /vault or /profile.
    "rate_floor": "",
}


def get_profile(conn: sqlite3.Connection) -> dict[str, str]:
    rows = {
        r["key"]: r["value"]
        for r in conn.execute(
            f"SELECT key, value FROM profile WHERE key IN ({','.join('?' for _ in FIELDS)})",
            FIELDS,
        )
    }
    return {field: rows.get(field) or DEFAULTS[field] for field in FIELDS}


def set_profile(conn: sqlite3.Connection, values: dict[str, str]) -> None:
    for field in FIELDS:
        if field not in values:
            continue
        conn.execute(
            "INSERT INTO profile (key, value) VALUES (?, ?) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            (field, values[field]),
        )
    conn.commit()
