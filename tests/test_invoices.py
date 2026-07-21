from __future__ import annotations

from pathlib import Path

from vamp import db as vamp_db
from vamp.config import load_config
from vamp.gigs import invoices, pipeline


def _conn_and_config(vamp_home: Path):
    config = load_config(home=vamp_home)
    return vamp_db.get_connection(config.db_path), config


def test_next_invoice_number_starts_at_0001(vamp_home: Path):
    conn, _ = _conn_and_config(vamp_home)
    try:
        assert invoices.next_invoice_number(conn) == "INV-0001"
    finally:
        conn.close()


def test_next_invoice_number_is_sequential(vamp_home: Path):
    conn, config = _conn_and_config(vamp_home)
    try:
        gig_id = pipeline.create_gig(conn, {"venue": "A", "date": "2026-01-01", "pay_agreed": 100})
        gig = pipeline.get_gig(conn, gig_id)
        invoices.create_invoice(conn, config.home, gig)
        invoices.create_invoice(conn, config.home, gig)
        third = invoices.next_invoice_number(conn)
        assert third == "INV-0003"
    finally:
        conn.close()


def test_next_invoice_number_is_gap_tolerant(vamp_home: Path):
    """Deleting an invoice must never free up its number for reuse — the
    next number is always max(existing) + 1, not a row count."""
    conn, config = _conn_and_config(vamp_home)
    try:
        gig_id = pipeline.create_gig(conn, {"venue": "A", "date": "2026-01-01", "pay_agreed": 100})
        gig = pipeline.get_gig(conn, gig_id)
        first_id = invoices.create_invoice(conn, config.home, gig)
        invoices.create_invoice(conn, config.home, gig)
        conn.execute("DELETE FROM invoices WHERE id = ?", (first_id,))
        conn.commit()
        assert invoices.next_invoice_number(conn) == "INV-0003"
    finally:
        conn.close()


def test_create_invoice_writes_self_contained_html(vamp_home: Path):
    conn, config = _conn_and_config(vamp_home)
    try:
        gig_id = pipeline.create_gig(
            conn, {"venue": "Vast", "date": "2026-08-01", "pay_agreed": 250}
        )
        gig = pipeline.get_gig(conn, gig_id)
        invoice_id = invoices.create_invoice(conn, config.home, gig)
        row = invoices.get_invoice(conn, invoice_id)
        assert row["number"] == "INV-0001"
        assert row["amount"] == 250
        assert row["paid_at"] is None
        html_path = Path(row["html_path"])
        assert html_path.exists()
        doc = html_path.read_text()
        assert "<!doctype html>" in doc
        assert "INV-0001" in doc
        assert "Vast" in doc
        assert "$250.00" in doc
        assert "UNPAID" in doc
    finally:
        conn.close()


def test_create_invoice_defaults_amount_to_pay_agreed(vamp_home: Path):
    conn, config = _conn_and_config(vamp_home)
    try:
        gig_id = pipeline.create_gig(
            conn, {"venue": "Skirvin", "date": "2026-08-01", "pay_agreed": 400}
        )
        gig = pipeline.get_gig(conn, gig_id)
        invoice_id = invoices.create_invoice(conn, config.home, gig)
        assert invoices.get_invoice(conn, invoice_id)["amount"] == 400
    finally:
        conn.close()


def test_create_invoice_accepts_explicit_amount_override(vamp_home: Path):
    conn, config = _conn_and_config(vamp_home)
    try:
        gig_id = pipeline.create_gig(
            conn, {"venue": "Skirvin", "date": "2026-08-01", "pay_agreed": 400}
        )
        gig = pipeline.get_gig(conn, gig_id)
        invoice_id = invoices.create_invoice(conn, config.home, gig, amount=350)
        assert invoices.get_invoice(conn, invoice_id)["amount"] == 350
    finally:
        conn.close()


def test_mark_invoice_paid_stamps_paid_at_and_regenerates_html(vamp_home: Path):
    conn, config = _conn_and_config(vamp_home)
    try:
        gig_id = pipeline.create_gig(
            conn, {"venue": "Vast", "date": "2026-08-01", "pay_agreed": 250}
        )
        gig = pipeline.get_gig(conn, gig_id)
        invoice_id = invoices.create_invoice(conn, config.home, gig)

        invoices.mark_invoice_paid(conn, config.home, invoice_id, paid_at="2026-08-05 10:00:00")

        row = invoices.get_invoice(conn, invoice_id)
        assert row["paid_at"] == "2026-08-05 10:00:00"
        doc = Path(row["html_path"]).read_text()
        assert "PAID" in doc
        assert "2026-08-05 10:00:00" in doc
    finally:
        conn.close()
