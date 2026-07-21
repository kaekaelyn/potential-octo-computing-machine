"""Metrics aggregations (PLAN.md §7/§12 M7)."""

from __future__ import annotations

import sqlite3

from vamp.gigs import income as income_service

# Prospect pipeline states (vamp.prospects.pipeline.PIPELINE_STATES) grouped
# into the funnel PLAN.md §7 asks for. These are *current*-state counts, not
# historical event counts: a prospect only shows up once, at its current
# stage, since the pipeline itself never records "went from contacted to
# in_conversation on this date" separately from the status column.
PITCHED_STATES: tuple[str, ...] = (
    "contacted",
    "follow_up_1",
    "follow_up_2",
    "in_conversation",
    "booked",
    "recurring",
    "dead",
)
RESPONDED_STATES: tuple[str, ...] = ("in_conversation", "booked", "recurring")
BOOKED_STATES: tuple[str, ...] = ("booked", "recurring")


def pipeline_funnel(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Per-category funnel: how many prospects have been pitched, how many
    responded, how many booked."""
    pitched_ph = ",".join("?" for _ in PITCHED_STATES)
    responded_ph = ",".join("?" for _ in RESPONDED_STATES)
    booked_ph = ",".join("?" for _ in BOOKED_STATES)
    return conn.execute(
        f"""
        SELECT COALESCE(category, 'uncategorized') AS category,
               SUM(CASE WHEN status IN ({pitched_ph}) THEN 1 ELSE 0 END) AS pitched,
               SUM(CASE WHEN status IN ({responded_ph}) THEN 1 ELSE 0 END) AS responded,
               SUM(CASE WHEN status IN ({booked_ph}) THEN 1 ELSE 0 END) AS booked
        FROM prospects
        GROUP BY category
        ORDER BY category COLLATE NOCASE
        """,
        (*PITCHED_STATES, *RESPONDED_STATES, *BOOKED_STATES),
    ).fetchall()


def source_conversion(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Leads captured per source vs. how many became an actual gig (linked
    via ``gigs.lead_id``) — the honest signal a lead turned into paid work,
    since ``leads.state`` has no UI path that ever sets it to 'booked'."""
    return conn.execute(
        """
        SELECT s.id AS source_id, s.name AS source_name, s.kind AS source_kind,
               COUNT(DISTINCT l.id) AS leads,
               COUNT(DISTINCT g.id) AS gigs
        FROM sources s
        LEFT JOIN leads l ON l.source_id = s.id
        LEFT JOIN gigs g ON g.lead_id = l.id
        GROUP BY s.id
        ORDER BY leads DESC, source_name COLLATE NOCASE
        """
    ).fetchall()


def dashboard(conn: sqlite3.Connection) -> dict:
    return {
        "funnel": pipeline_funnel(conn),
        "sources": source_conversion(conn),
        "income_by_month": income_service.monthly_totals(conn),
    }
