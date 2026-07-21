from __future__ import annotations

from pathlib import Path

from vamp import db as vamp_db
from vamp.config import load_config
from vamp.gigs import income, pipeline


def _conn(vamp_home: Path):
    return vamp_db.get_connection(load_config(home=vamp_home).db_path)


def test_monthly_totals_group_by_paid_month(vamp_home: Path):
    conn = _conn(vamp_home)
    try:
        g1 = pipeline.create_gig(conn, {"venue": "A", "date": "2026-01-15", "pay_agreed": 200})
        conn.execute(
            "UPDATE gigs SET pay_received = 200, paid_at = '2026-01-20 00:00:00' WHERE id = ?",
            (g1,),
        )
        g2 = pipeline.create_gig(conn, {"venue": "B", "date": "2026-02-01", "pay_agreed": 100})
        # No paid_at recorded (cash the night of) — falls back to gig date.
        conn.execute("UPDATE gigs SET pay_received = 100 WHERE id = ?", (g2,))
        conn.commit()

        totals = {r["month"]: r["total"] for r in income.monthly_totals(conn)}
        assert totals == {"2026-01": 200, "2026-02": 100}
    finally:
        conn.close()


def test_category_totals_group_by_prospect_category(vamp_home: Path):
    conn = _conn(vamp_home)
    try:
        pid = conn.execute(
            "INSERT INTO prospects (name, category, status, verified) "
            "VALUES ('Vast', 'hotel', 'booked', 1)"
        ).lastrowid
        conn.commit()
        gid = pipeline.create_gig(
            conn, {"prospect_id": pid, "venue": "Vast", "date": "2026-01-15", "pay_agreed": 200}
        )
        conn.execute("UPDATE gigs SET pay_received = 200 WHERE id = ?", (gid,))
        conn.commit()

        totals = {r["category"]: r["total"] for r in income.category_totals(conn)}
        assert totals == {"hotel": 200}
    finally:
        conn.close()


def test_category_totals_falls_back_to_uncategorized(vamp_home: Path):
    conn = _conn(vamp_home)
    try:
        gid = pipeline.create_gig(conn, {"venue": "Somewhere", "date": "2026-01-15"})
        conn.execute("UPDATE gigs SET pay_received = 50 WHERE id = ?", (gid,))
        conn.commit()

        totals = {r["category"]: r["total"] for r in income.category_totals(conn)}
        assert totals == {"uncategorized": 50}
    finally:
        conn.close()


def test_pipeline_value_sums_confirmed_future_gigs_only(vamp_home: Path):
    conn = _conn(vamp_home)
    try:
        future_confirmed = pipeline.create_gig(
            conn, {"venue": "A", "date": "2099-01-01", "pay_agreed": 300}
        )
        pipeline.set_state(conn, future_confirmed, "confirmed")
        past_confirmed = pipeline.create_gig(
            conn, {"venue": "B", "date": "2000-01-01", "pay_agreed": 500}
        )
        pipeline.set_state(conn, past_confirmed, "confirmed")
        # Still 'offered' (never confirmed) — must not count toward pipeline value.
        pipeline.create_gig(conn, {"venue": "C", "date": "2099-01-01", "pay_agreed": 999})

        value = income.pipeline_value(conn, today="2026-07-21")
        assert value == 300
    finally:
        conn.close()
