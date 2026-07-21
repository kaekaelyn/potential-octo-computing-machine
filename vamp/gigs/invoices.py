"""Invoices: numbered, print-ready, self-contained HTML (PLAN.md §8/§12 M6).

No payment processing — this is the paper trail only. Generating or
"marking paid" an invoice never sends anything anywhere (CLAUDE.md: no
auto-sending); the file is meant to be attached, printed to PDF, or handed
over in person, the same self-contained-HTML shape as the EPK export
(``vamp/vault/epk.py``).
"""

from __future__ import annotations

import html
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from vamp.profile import service as profile_service

INVOICE_PREFIX = "INV-"
_NUMBER_RE = re.compile(rf"^{re.escape(INVOICE_PREFIX)}(\d+)$")

_STYLE = """
  body { font-family: Georgia, 'Times New Roman', serif; max-width: 38rem;
         margin: 2rem auto; padding: 0 1.25rem; color: #1b1b1b; line-height: 1.5; }
  h1 { margin-bottom: 0; }
  .status { display: inline-block; border-radius: 999px; padding: 0.1rem 0.7rem;
            font-size: 0.85rem; margin-top: 0.5rem; }
  .status-paid { background: #2f8f4e; color: #fff; }
  .status-unpaid { border: 1px solid #b3392c; color: #b3392c; }
  table { width: 100%; border-collapse: collapse; margin: 1.5rem 0; }
  td, th { text-align: left; padding: 0.4rem 0; border-bottom: 1px solid #ccc; }
  .amount { text-align: right; font-size: 1.2rem; font-weight: bold; }
  .meta { color: #6b6b6b; font-size: 0.9rem; }
"""


def _now_str() -> str:
    return datetime.now(UTC).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")


def next_invoice_number(conn: sqlite3.Connection) -> str:
    """Sequential and gap-tolerant: the highest existing numeric suffix + 1,
    not a row count, so a deleted invoice can never cause a collision."""
    rows = conn.execute("SELECT number FROM invoices").fetchall()
    highest = 0
    for row in rows:
        match = _NUMBER_RE.match(row["number"] or "")
        if match:
            highest = max(highest, int(match.group(1)))
    return f"{INVOICE_PREFIX}{highest + 1:04d}"


def _esc(value) -> str:
    return html.escape(str(value)) if value is not None else ""


def generate_invoice_html(
    number: str,
    gig: sqlite3.Row,
    profile: dict,
    amount: float,
    issued_at: str,
    paid_at: str | None,
) -> str:
    status_html = (
        '<span class="status status-paid">PAID</span>'
        if paid_at
        else '<span class="status status-unpaid">UNPAID</span>'
    )
    paid_line = f'<p class="meta">Paid {_esc(paid_at)}</p>' if paid_at else ""
    from_line = (
        f"{_esc(profile.get('display_name'))} — {_esc(profile.get('instrument'))}, "
        f"{_esc(profile.get('home_area'))}"
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Invoice {_esc(number)}</title>
<style>{_STYLE}</style>
</head>
<body>
<h1>Invoice {_esc(number)}</h1>
<p class="meta">Issued {_esc(issued_at)}</p>
{status_html}
{paid_line}

<table>
  <tr><th>From</th><td>{from_line}</td></tr>
  <tr><th>Billed to</th><td>{_esc(gig["venue"] or "venue TBD")}</td></tr>
  <tr><th>Gig date</th><td>{_esc(gig["date"] or "TBD")}</td></tr>
</table>

<table>
  <tr><th>Description</th><th class="amount">Amount</th></tr>
  <tr><td>Live music performance — {_esc(gig["venue"] or "engagement")}</td>
      <td class="amount">${amount:,.2f}</td></tr>
</table>

<p class="meta">No online payment is collected through this document — it's a paper
trail only. Pay by whatever means you and {_esc(profile.get("display_name"))} agreed.</p>
</body>
</html>
"""


def create_invoice(
    conn: sqlite3.Connection, vamp_home: Path, gig: sqlite3.Row, amount: float | None = None
) -> int:
    amount = amount if amount is not None else (gig["pay_agreed"] or 0.0)
    number = next_invoice_number(conn)
    issued_at = _now_str()
    profile = profile_service.get_profile(conn)
    doc = generate_invoice_html(number, gig, profile, amount, issued_at, None)

    out_dir = vamp_home / "invoices"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{number}.html"
    out_path.write_text(doc)

    cur = conn.execute(
        "INSERT INTO invoices (gig_id, number, issued_at, paid_at, amount, html_path) "
        "VALUES (?, ?, ?, NULL, ?, ?)",
        (gig["id"], number, issued_at, amount, str(out_path)),
    )
    conn.commit()
    return cur.lastrowid


def list_invoices_for_gig(conn: sqlite3.Connection, gig_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM invoices WHERE gig_id = ? ORDER BY id DESC", (gig_id,)
    ).fetchall()


def get_invoice(conn: sqlite3.Connection, invoice_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()


def mark_invoice_paid(
    conn: sqlite3.Connection, vamp_home: Path, invoice_id: int, paid_at: str | None = None
) -> None:
    """Stamp the invoice paid, regenerate its HTML so the downloadable copy
    reflects PAID, and return the owning gig row (routes wire the rest of
    the lifecycle — pay_received, gig state — from there)."""
    invoice = get_invoice(conn, invoice_id)
    if invoice is None:
        raise ValueError(f"no invoice {invoice_id}")
    paid_at = paid_at or _now_str()
    conn.execute("UPDATE invoices SET paid_at = ? WHERE id = ?", (paid_at, invoice_id))
    conn.commit()

    gig = conn.execute("SELECT * FROM gigs WHERE id = ?", (invoice["gig_id"],)).fetchone()
    if gig is not None:
        profile = profile_service.get_profile(conn)
        doc = generate_invoice_html(
            invoice["number"], gig, profile, invoice["amount"], invoice["issued_at"], paid_at
        )
        Path(invoice["html_path"]).write_text(doc)
