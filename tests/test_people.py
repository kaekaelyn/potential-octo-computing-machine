from __future__ import annotations

from pathlib import Path

from vamp import db as vamp_db
from vamp.config import load_config
from vamp.gigs import pipeline as gigs_pipeline
from vamp.people import service


def _conn(vamp_home: Path):
    return vamp_db.get_connection(load_config(home=vamp_home).db_path)


def test_create_and_get_person(vamp_home: Path):
    conn = _conn(vamp_home)
    try:
        pid = service.create_person(
            conn,
            {
                "name": "Jane Doe",
                "role": "planner",
                "phone": "555-1234",
                "email": "jane@example.com",
            },
        )
        row = service.get_person(conn, pid)
        assert row["name"] == "Jane Doe"
        assert row["role"] == "planner"
        contact = service.contact_fields(row)
        assert contact == {"phone": "555-1234", "email": "jane@example.com"}
    finally:
        conn.close()


def test_update_person(vamp_home: Path):
    conn = _conn(vamp_home)
    try:
        pid = service.create_person(conn, {"name": "Jane Doe"})
        service.update_person(conn, pid, {"name": "Jane Doe", "role": "worship leader"})
        assert service.get_person(conn, pid)["role"] == "worship leader"
    finally:
        conn.close()


def test_delete_person_cleans_up_referrals(vamp_home: Path):
    conn = _conn(vamp_home)
    try:
        pid = service.create_person(conn, {"name": "Jane Doe"})
        gid = gigs_pipeline.create_gig(conn, {"venue": "Vast"})
        service.add_referral(conn, pid, gid)

        service.delete_person(conn, pid)

        assert service.get_person(conn, pid) is None
        n = conn.execute(
            "SELECT COUNT(*) AS n FROM referrals WHERE person_id = ?", (pid,)
        ).fetchone()["n"]
        assert n == 0
    finally:
        conn.close()


def test_referral_chain_person_to_gig(vamp_home: Path):
    conn = _conn(vamp_home)
    try:
        pid = service.create_person(conn, {"name": "Jane Doe"})
        gid = gigs_pipeline.create_gig(
            conn, {"venue": "Vast", "date": "2026-09-01", "pay_agreed": 300}
        )
        service.add_referral(conn, pid, gid)

        referred = service.referrals_for_person(conn, pid)
        assert len(referred) == 1
        assert referred[0]["gig_id"] == gid
        assert referred[0]["venue"] == "Vast"

        referrers = service.referrals_for_gig(conn, gid)
        assert len(referrers) == 1
        assert referrers[0]["name"] == "Jane Doe"
    finally:
        conn.close()


def test_remove_referral(vamp_home: Path):
    conn = _conn(vamp_home)
    try:
        pid = service.create_person(conn, {"name": "Jane Doe"})
        gid = gigs_pipeline.create_gig(conn, {"venue": "Vast"})
        referral_id = service.add_referral(conn, pid, gid)

        service.remove_referral(conn, referral_id)

        assert service.referrals_for_person(conn, pid) == []
    finally:
        conn.close()
