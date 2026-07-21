"""Income dashboard (PLAN.md §8/§12 M6): monthly totals, income by category,
and pipeline value — the numbers that keep the Paying/Stepping-stones split
honest (PLAN.md §13).
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime


def _today_str() -> str:
    return datetime.now(UTC).date().isoformat()


def monthly_totals(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Money actually received, grouped by the month it arrived — falls
    back to the gig date when ``paid_at`` wasn't recorded (e.g. cash in
    hand the night of, never formally moved to the 'paid' state)."""
    return conn.execute(
        """
        SELECT strftime('%Y-%m', COALESCE(paid_at, date)) AS month,
               SUM(pay_received) AS total
        FROM gigs
        WHERE pay_received IS NOT NULL AND pay_received > 0
        GROUP BY month
        ORDER BY month DESC
        """
    ).fetchall()


def category_totals(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Received income grouped by the linked prospect's category, falling
    back to the source lead's kind, then 'uncategorized'."""
    return conn.execute(
        """
        SELECT COALESCE(p.category, l.kind, 'uncategorized') AS category,
               SUM(g.pay_received) AS total
        FROM gigs g
        LEFT JOIN prospects p ON p.id = g.prospect_id
        LEFT JOIN leads l ON l.id = g.lead_id
        WHERE g.pay_received IS NOT NULL AND g.pay_received > 0
        GROUP BY category
        ORDER BY total DESC
        """
    ).fetchall()


def year_totals(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT strftime('%Y', COALESCE(paid_at, date)) AS year, SUM(pay_received) AS total
        FROM gigs
        WHERE pay_received IS NOT NULL AND pay_received > 0
        GROUP BY year
        ORDER BY year DESC
        """
    ).fetchall()


def pipeline_value(conn: sqlite3.Connection, today: str | None = None) -> float:
    """Confirmed-future gigs: money reasonably expected to arrive
    (PLAN.md §8 "pipeline value (confirmed-future gigs)")."""
    today = today or _today_str()
    row = conn.execute(
        "SELECT COALESCE(SUM(pay_agreed), 0) AS total FROM gigs "
        "WHERE state = 'confirmed' AND date IS NOT NULL AND date >= ?",
        (today,),
    ).fetchone()
    return row["total"] or 0.0


def dashboard(conn: sqlite3.Connection) -> dict:
    return {
        "monthly": monthly_totals(conn),
        "by_category": category_totals(conn),
        "yearly": year_totals(conn),
        "pipeline_value": pipeline_value(conn),
    }
