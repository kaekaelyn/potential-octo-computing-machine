"""People CRUD + referral chains (``people``/``referrals`` tables,
PLAN.md §7/§10). A referral links a person to a gig they led to — Vamp
never guesses this; it's always logged by hand after the fact."""

from __future__ import annotations

import json
import sqlite3

_EDITABLE_COLUMNS: tuple[str, ...] = ("name", "role", "org", "met_at", "notes")


def list_people(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM people ORDER BY name COLLATE NOCASE").fetchall()


def get_person(conn: sqlite3.Connection, person_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM people WHERE id = ?", (person_id,)).fetchone()


def _contact_json(fields: dict) -> str | None:
    contact = {k: fields[k] for k in ("phone", "email") if fields.get(k)}
    return json.dumps(contact) if contact else None


def create_person(conn: sqlite3.Connection, fields: dict) -> int:
    cur = conn.execute(
        "INSERT INTO people (name, role, org, met_at, contact_json, notes) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            fields.get("name"),
            fields.get("role"),
            fields.get("org"),
            fields.get("met_at"),
            _contact_json(fields),
            fields.get("notes"),
        ),
    )
    conn.commit()
    return cur.lastrowid


def update_person(conn: sqlite3.Connection, person_id: int, fields: dict) -> None:
    conn.execute(
        "UPDATE people SET name = ?, role = ?, org = ?, met_at = ?, contact_json = ?, "
        "notes = ? WHERE id = ?",
        (
            fields.get("name"),
            fields.get("role"),
            fields.get("org"),
            fields.get("met_at"),
            _contact_json(fields),
            fields.get("notes"),
            person_id,
        ),
    )
    conn.commit()


def delete_person(conn: sqlite3.Connection, person_id: int) -> None:
    conn.execute("DELETE FROM referrals WHERE person_id = ?", (person_id,))
    conn.execute("DELETE FROM people WHERE id = ?", (person_id,))
    conn.commit()


def contact_fields(person: sqlite3.Row) -> dict:
    return json.loads(person["contact_json"] or "{}")


def add_referral(conn: sqlite3.Connection, person_id: int, gig_id: int) -> int:
    cur = conn.execute(
        "INSERT INTO referrals (person_id, gig_id) VALUES (?, ?)", (person_id, gig_id)
    )
    conn.commit()
    return cur.lastrowid


def remove_referral(conn: sqlite3.Connection, referral_id: int) -> None:
    conn.execute("DELETE FROM referrals WHERE id = ?", (referral_id,))
    conn.commit()


def referrals_for_person(conn: sqlite3.Connection, person_id: int) -> list[sqlite3.Row]:
    """Gigs this person referred — the referral chain, person → gig."""
    return conn.execute(
        """
        SELECT r.id AS referral_id, g.id AS gig_id, g.venue, g.date, g.pay_agreed, g.state
        FROM referrals r
        JOIN gigs g ON g.id = r.gig_id
        WHERE r.person_id = ?
        ORDER BY g.date DESC, g.id DESC
        """,
        (person_id,),
    ).fetchall()


def referrals_for_gig(conn: sqlite3.Connection, gig_id: int) -> list[sqlite3.Row]:
    """Who's credited with referring this gig — a gig may have more than
    one contributing referral (a planner introduced you, a musician
    friend vouched)."""
    return conn.execute(
        """
        SELECT r.id AS referral_id, p.id AS person_id, p.name, p.role, p.org
        FROM referrals r
        JOIN people p ON p.id = r.person_id
        WHERE r.gig_id = ?
        ORDER BY p.name COLLATE NOCASE
        """,
        (gig_id,),
    ).fetchall()
