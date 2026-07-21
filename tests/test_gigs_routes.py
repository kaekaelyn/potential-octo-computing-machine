from __future__ import annotations

from pathlib import Path

from vamp import db as vamp_db
from vamp.app import create_app
from vamp.config import load_config
from vamp.gigs import pipeline
from vamp.profile import service as profile_service


def _client(vamp_home: Path):
    config = load_config(home=vamp_home)
    app = create_app(config)
    app.testing = True
    return app.test_client(), config


def test_create_gig_and_view_detail(vamp_home: Path):
    client, config = _client(vamp_home)
    resp = client.post(
        "/gigs", data={"venue": "Skirvin", "date": "2026-09-01", "pay_agreed": "300"}
    )
    assert resp.status_code == 302
    conn = vamp_db.get_connection(config.db_path)
    try:
        gig_id = conn.execute("SELECT id FROM gigs WHERE venue = 'Skirvin'").fetchone()["id"]
    finally:
        conn.close()
    body = client.get(f"/gigs/{gig_id}").get_data(as_text=True)
    assert "Skirvin" in body
    assert "Offered" in body


def test_advance_route_moves_state(vamp_home: Path):
    client, config = _client(vamp_home)
    client.post("/gigs", data={"venue": "Vast"})
    conn = vamp_db.get_connection(config.db_path)
    try:
        gig_id = conn.execute("SELECT id FROM gigs WHERE venue = 'Vast'").fetchone()["id"]
    finally:
        conn.close()
    client.post(f"/gigs/{gig_id}/advance")
    conn = vamp_db.get_connection(config.db_path)
    try:
        assert conn.execute("SELECT state FROM gigs WHERE id = ?", (gig_id,)).fetchone()[
            "state"
        ] == ("confirmed")
    finally:
        conn.close()


def test_full_lifecycle_through_invoice_and_payment(vamp_home: Path):
    client, config = _client(vamp_home)
    client.post("/gigs", data={"venue": "Vast", "date": "2026-01-01", "pay_agreed": "300"})
    conn = vamp_db.get_connection(config.db_path)
    try:
        gig_id = conn.execute("SELECT id FROM gigs WHERE venue = 'Vast'").fetchone()["id"]
    finally:
        conn.close()

    client.post(f"/gigs/{gig_id}/status", data={"state": "confirmed"})
    client.post(f"/gigs/{gig_id}/status", data={"state": "played"})
    client.post(f"/gigs/{gig_id}/invoice", data={})

    conn = vamp_db.get_connection(config.db_path)
    try:
        invoice = conn.execute("SELECT * FROM invoices WHERE gig_id = ?", (gig_id,)).fetchone()
    finally:
        conn.close()
    assert invoice["number"] == "INV-0001"

    download = client.get(f"/gigs/invoices/{invoice['id']}/download")
    assert download.status_code == 200
    assert "INV-0001" in download.get_data(as_text=True)

    resp = client.post(f"/gigs/invoices/{invoice['id']}/mark-paid")
    assert resp.status_code == 302

    conn = vamp_db.get_connection(config.db_path)
    try:
        gig = conn.execute("SELECT * FROM gigs WHERE id = ?", (gig_id,)).fetchone()
        assert gig["state"] == "paid"
        assert gig["pay_received"] == 300
        open_reminders = conn.execute(
            "SELECT COUNT(*) AS n FROM reminders WHERE ref_kind = ? AND ref_id = ? AND done = 0",
            (pipeline.CHASE_UNPAID_REF_KIND, gig_id),
        ).fetchone()["n"]
        assert open_reminders == 0
    finally:
        conn.close()


def test_below_floor_chip_appears_unless_strategic(vamp_home: Path):
    client, config = _client(vamp_home)
    conn = vamp_db.get_connection(config.db_path)
    try:
        profile_service.set_profile(conn, {"rate_floor": "200"})
    finally:
        conn.close()

    client.post("/gigs", data={"venue": "Cheap Gig", "date": "2026-01-01", "pay_agreed": "100"})
    body = client.get("/gigs").get_data(as_text=True)
    assert "−below-floor" in body

    conn = vamp_db.get_connection(config.db_path)
    try:
        gig_id = conn.execute("SELECT id FROM gigs WHERE venue = 'Cheap Gig'").fetchone()["id"]
    finally:
        conn.close()

    client.post(
        f"/gigs/{gig_id}/edit",
        data={"venue": "Cheap Gig", "pay_agreed": "100", "strategic": "on"},
    )
    body = client.get("/gigs").get_data(as_text=True)
    assert "−below-floor" not in body


def test_income_page_renders(vamp_home: Path):
    client, _ = _client(vamp_home)
    body = client.get("/gigs/income").get_data(as_text=True)
    assert "Income" in body
    assert "Pipeline value" in body
