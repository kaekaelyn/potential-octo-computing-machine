"""Requirement↔asset matching: keeps ``requirements.satisfied_asset_id``
in sync with the vault, and answers "READY or Missing?" for lead cards
plus the unlock report (PLAN.md §5).

A requirement is satisfied by the most recently updated *ready* asset of
the matching kind — good enough for a single-user vault where "the
current headshot" is unambiguous.
"""

from __future__ import annotations

import sqlite3

from vamp.requirements.kinds import ASSET_LABELS, REQUIREMENT_LABELS, REQUIREMENT_TO_ASSET_KIND
from vamp.requirements.parser import parse_requirements

# Assets no longer need building for these lead states — booked/passed/
# excluded opportunities don't count against the unlock report.
OPEN_LEAD_STATES = ("inbox", "interested", "preparing", "applied")


def best_asset_id(conn: sqlite3.Connection, asset_kind: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM assets WHERE kind = ? AND ready = 1 "
        "ORDER BY updated_at DESC, id DESC LIMIT 1",
        (asset_kind,),
    ).fetchone()
    return row["id"] if row else None


def sync_requirements(conn: sqlite3.Connection, lead_id: int, text: str) -> None:
    """Re-parse ``text`` and upsert this lead's ``requirements`` rows,
    matching each against the current vault. Called on lead create and on
    finish-by-hand edits, since the text can change."""
    existing = {
        row["kind"]: row
        for row in conn.execute("SELECT * FROM requirements WHERE lead_id = ?", (lead_id,))
    }
    parsed = parse_requirements(text)
    parsed_kinds: set[str] = set()

    for req in parsed:
        parsed_kinds.add(req.kind)
        asset_kind = REQUIREMENT_TO_ASSET_KIND.get(req.kind)
        asset_id = best_asset_id(conn, asset_kind) if asset_kind else None
        if req.kind in existing:
            conn.execute(
                "UPDATE requirements SET detail = ?, satisfied_asset_id = ? WHERE id = ?",
                (req.detail, asset_id, existing[req.kind]["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO requirements (lead_id, kind, detail, satisfied_asset_id) "
                "VALUES (?, ?, ?, ?)",
                (lead_id, req.kind, req.detail, asset_id),
            )

    for kind, row in existing.items():
        if kind not in parsed_kinds:
            conn.execute("DELETE FROM requirements WHERE id = ?", (row["id"],))

    conn.commit()


def rematch_requirements_for_asset_kind(conn: sqlite3.Connection, asset_kind: str) -> None:
    """Re-run matching for every requirement kind satisfied by
    ``asset_kind`` — call this whenever an asset is created, edited,
    (un)readied, or deleted."""
    requirement_kinds = [k for k, a in REQUIREMENT_TO_ASSET_KIND.items() if a == asset_kind]
    if not requirement_kinds:
        return
    asset_id = best_asset_id(conn, asset_kind)
    placeholders = ",".join("?" for _ in requirement_kinds)
    conn.execute(
        f"UPDATE requirements SET satisfied_asset_id = ? WHERE kind IN ({placeholders})",
        (asset_id, *requirement_kinds),
    )
    conn.commit()


def lead_status(conn: sqlite3.Connection, lead_id: int) -> dict:
    """Full requirement checklist + READY status for one lead's detail page."""
    rows = conn.execute(
        "SELECT * FROM requirements WHERE lead_id = ? ORDER BY id", (lead_id,)
    ).fetchall()
    checklist = []
    trackable_missing = 0
    trackable_total = 0
    for row in rows:
        asset_kind = REQUIREMENT_TO_ASSET_KIND.get(row["kind"])
        satisfied = bool(row["satisfied_asset_id"])
        if asset_kind:
            trackable_total += 1
            if not satisfied:
                trackable_missing += 1
        checklist.append(
            {
                "id": row["id"],
                "kind": row["kind"],
                "label": REQUIREMENT_LABELS.get(row["kind"], row["kind"]),
                "detail": row["detail"],
                "trackable": asset_kind is not None,
                "satisfied": satisfied,
                "satisfied_asset_id": row["satisfied_asset_id"],
            }
        )
    return {
        "checklist": checklist,
        "ready": trackable_total > 0 and trackable_missing == 0,
        "has_requirements": trackable_total > 0,
    }


def status_for_leads(conn: sqlite3.Connection, lead_ids: list[int]) -> dict[int, dict]:
    """Compact READY/Missing status for a batch of leads — one query, used
    to badge the inbox lead cards without an N+1."""
    if not lead_ids:
        return {}
    placeholders = ",".join("?" for _ in lead_ids)
    rows = conn.execute(
        f"SELECT lead_id, kind, satisfied_asset_id FROM requirements "
        f"WHERE lead_id IN ({placeholders})",
        lead_ids,
    ).fetchall()
    by_lead: dict[int, list[sqlite3.Row]] = {lid: [] for lid in lead_ids}
    for row in rows:
        by_lead[row["lead_id"]].append(row)

    result: dict[int, dict] = {}
    for lead_id, reqs in by_lead.items():
        trackable = [r for r in reqs if REQUIREMENT_TO_ASSET_KIND.get(r["kind"])]
        missing = [r for r in trackable if not r["satisfied_asset_id"]]
        result[lead_id] = {
            "has_requirements": bool(trackable),
            "ready": bool(trackable) and not missing,
            "missing_labels": [REQUIREMENT_LABELS.get(r["kind"], r["kind"]) for r in missing],
        }
    return result


def unlock_report(conn: sqlite3.Connection) -> dict:
    """Which single missing asset kind would unlock the most open leads
    (PLAN.md §5): "One 3-minute live video unlocks 7 of your 11 open
    opportunities." """
    placeholders = ",".join("?" for _ in OPEN_LEAD_STATES)
    rows = conn.execute(
        f"""
        SELECT r.lead_id, r.kind, r.satisfied_asset_id
        FROM requirements r
        JOIN leads l ON l.id = r.lead_id
        WHERE l.state IN ({placeholders})
        """,
        OPEN_LEAD_STATES,
    ).fetchall()

    trackable = [r for r in rows if REQUIREMENT_TO_ASSET_KIND.get(r["kind"])]
    total_open = len({r["lead_id"] for r in trackable})

    counts: dict[str, set[int]] = {}
    for row in trackable:
        if row["satisfied_asset_id"]:
            continue
        asset_kind = REQUIREMENT_TO_ASSET_KIND[row["kind"]]
        counts.setdefault(asset_kind, set()).add(row["lead_id"])

    entries = sorted(
        (
            {"asset_kind": kind, "label": ASSET_LABELS.get(kind, kind), "lead_count": len(lead_ids)}
            for kind, lead_ids in counts.items()
        ),
        key=lambda e: (-e["lead_count"], e["label"]),
    )
    return {"total_open": total_open, "entries": entries}
