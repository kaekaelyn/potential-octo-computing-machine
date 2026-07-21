"""Gig routes: the lifecycle board, invoices, and the income dashboard
(PLAN.md §8/§12 M6)."""

from __future__ import annotations

from pathlib import Path

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from vamp import db as vamp_db
from vamp.gigs import income as income_service
from vamp.gigs import invoices as invoices_service
from vamp.gigs import pipeline
from vamp.money import floor as floor_service
from vamp.people import service as people_service

bp = Blueprint("gigs", __name__, url_prefix="/gigs")


def _conn():
    config = current_app.config["VAMP_CONFIG"]
    return vamp_db.get_connection(config.db_path)


def _vamp_home():
    return current_app.config["VAMP_CONFIG"].home


def _form_fields() -> dict:
    return {
        "prospect_id": request.form.get("prospect_id") or None,
        "lead_id": request.form.get("lead_id") or None,
        "date": (request.form.get("date") or "").strip() or None,
        "venue": (request.form.get("venue") or "").strip() or None,
        "pay_agreed": request.form.get("pay_agreed") or None,
        "pay_received": request.form.get("pay_received") or None,
        "expenses": request.form.get("expenses") or None,
        "mileage": request.form.get("mileage") or None,
        "notes": (request.form.get("notes") or "").strip() or None,
        "strategic": request.form.get("strategic") == "on",
    }


def _below_floor_ids(conn, rows) -> set[int]:
    floor = floor_service.get_rate_floor(conn)
    if floor is None:
        return set()
    return {
        r["id"]
        for r in rows
        if r["state"] != "played"
        and r["state"] != "paid"
        and not r["strategic"]
        and floor_service.is_below_floor(r["pay_agreed"], floor)
    }


@bp.route("")
def board():
    state = request.args.get("state") or None
    conn = _conn()
    try:
        rows = pipeline.list_gigs(conn, state=state)
        below_floor = _below_floor_ids(conn, rows)
        state_counts = conn.execute(
            "SELECT state, COUNT(*) AS n FROM gigs GROUP BY state"
        ).fetchall()
    finally:
        conn.close()
    return render_template(
        "gigs/board.html",
        gigs=rows,
        below_floor=below_floor,
        states=pipeline.GIG_STATES,
        state_labels=pipeline.STATE_LABELS,
        state_counts={r["state"]: r["n"] for r in state_counts},
        active_state=state,
    )


@bp.route("", methods=["POST"])
def create():
    fields = _form_fields()
    conn = _conn()
    try:
        gig_id = pipeline.create_gig(conn, fields)
    finally:
        conn.close()
    flash("Gig added as offered.", "info")
    return redirect(url_for("gigs.detail", gig_id=gig_id))


@bp.route("/<int:gig_id>")
def detail(gig_id: int):
    conn = _conn()
    try:
        gig = pipeline.get_gig(conn, gig_id)
        if gig is None:
            abort(404)
        invoices = invoices_service.list_invoices_for_gig(conn, gig_id)
        referrals = people_service.referrals_for_gig(conn, gig_id)
        people = people_service.list_people(conn)
        chase_reminder = conn.execute(
            "SELECT * FROM reminders WHERE ref_kind = ? AND ref_id = ? "
            "ORDER BY done, due_at DESC LIMIT 1",
            (pipeline.CHASE_UNPAID_REF_KIND, gig_id),
        ).fetchone()
        floor = floor_service.get_rate_floor(conn)
        below_floor = (
            gig["state"] not in ("played", "paid")
            and not gig["strategic"]
            and floor_service.is_below_floor(gig["pay_agreed"], floor)
        )
    finally:
        conn.close()
    return render_template(
        "gigs/detail.html",
        g=gig,
        invoices=invoices,
        referrals=referrals,
        people=people,
        chase_reminder=chase_reminder,
        below_floor=below_floor,
        states=pipeline.GIG_STATES,
        state_labels=pipeline.STATE_LABELS,
        next_state=pipeline.next_state(gig["state"]),
    )


@bp.route("/<int:gig_id>/edit", methods=["POST"])
def edit(gig_id: int):
    conn = _conn()
    try:
        if pipeline.get_gig(conn, gig_id) is None:
            abort(404)
        pipeline.update_gig(conn, gig_id, _form_fields())
    finally:
        conn.close()
    flash("Gig updated.", "info")
    return redirect(url_for("gigs.detail", gig_id=gig_id))


@bp.route("/<int:gig_id>/status", methods=["POST"])
def set_status(gig_id: int):
    new_state = (request.form.get("state") or "").strip()
    conn = _conn()
    try:
        if pipeline.get_gig(conn, gig_id) is None:
            abort(404)
        if new_state not in pipeline.GIG_STATES:
            flash("Unknown gig state.", "error")
            return redirect(url_for("gigs.detail", gig_id=gig_id))
        pipeline.set_state(conn, gig_id, new_state)
    finally:
        conn.close()
    return redirect(url_for("gigs.detail", gig_id=gig_id))


@bp.route("/<int:gig_id>/advance", methods=["POST"])
def advance(gig_id: int):
    conn = _conn()
    try:
        if pipeline.get_gig(conn, gig_id) is None:
            abort(404)
        pipeline.advance_state(conn, gig_id)
    finally:
        conn.close()
    return redirect(url_for("gigs.detail", gig_id=gig_id))


@bp.route("/<int:gig_id>/delete", methods=["POST"])
def delete(gig_id: int):
    conn = _conn()
    try:
        if pipeline.get_gig(conn, gig_id) is None:
            abort(404)
        pipeline.delete_gig(conn, gig_id)
    finally:
        conn.close()
    flash("Gig removed.", "info")
    return redirect(url_for("gigs.board"))


@bp.route("/<int:gig_id>/invoice", methods=["POST"])
def create_invoice(gig_id: int):
    amount = request.form.get("amount") or None
    conn = _conn()
    try:
        gig = pipeline.get_gig(conn, gig_id)
        if gig is None:
            abort(404)
        invoices_service.create_invoice(
            conn, _vamp_home(), gig, amount=float(amount) if amount else None
        )
    finally:
        conn.close()
    flash("Invoice created.", "info")
    return redirect(url_for("gigs.detail", gig_id=gig_id))


@bp.route("/invoices/<int:invoice_id>/download")
def download_invoice(invoice_id: int):
    conn = _conn()
    try:
        invoice = invoices_service.get_invoice(conn, invoice_id)
    finally:
        conn.close()
    if invoice is None:
        abort(404)
    html_doc = Path(invoice["html_path"]).read_text()
    return Response(
        html_doc,
        mimetype="text/html",
        headers={"Content-Disposition": f"attachment; filename={invoice['number']}.html"},
    )


@bp.route("/invoices/<int:invoice_id>/mark-paid", methods=["POST"])
def mark_invoice_paid(invoice_id: int):
    conn = _conn()
    try:
        invoice = invoices_service.get_invoice(conn, invoice_id)
        if invoice is None:
            abort(404)
        invoices_service.mark_invoice_paid(conn, _vamp_home(), invoice_id)
        gig = pipeline.get_gig(conn, invoice["gig_id"])
        if gig is not None:
            if gig["pay_received"] is None:
                conn.execute(
                    "UPDATE gigs SET pay_received = ? WHERE id = ?",
                    (invoice["amount"], gig["id"]),
                )
                conn.commit()
            pipeline.set_state(conn, gig["id"], "paid")
    finally:
        conn.close()
    flash("Invoice marked paid; gig moved to paid.", "info")
    return redirect(url_for("gigs.detail", gig_id=invoice["gig_id"]))


@bp.route("/income")
def income():
    conn = _conn()
    try:
        data = income_service.dashboard(conn)
        rate_ranges = conn.execute(
            "SELECT * FROM rate_ranges ORDER BY gig_type COLLATE NOCASE"
        ).fetchall()
        current_floor = floor_service.get_rate_floor(conn)
    finally:
        conn.close()
    return render_template(
        "gigs/income.html", data=data, rate_ranges=rate_ranges, current_floor=current_floor
    )
