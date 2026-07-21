"""Leads routes: the Paying/Stepping-stones inbox, the Excluded shelf with
one-tap restore, and the finish-by-hand detail/edit view (PLAN.md §4)."""

from __future__ import annotations

from flask import Blueprint, abort, current_app, redirect, render_template, request, url_for

from vamp import db as vamp_db
from vamp.filters import REASON_CHIP
from vamp.leads import service

bp = Blueprint("leads", __name__)


def _conn():
    config = current_app.config["VAMP_CONFIG"]
    return vamp_db.get_connection(config.db_path)


@bp.route("/leads")
def inbox():
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT * FROM leads WHERE state != 'excluded' ORDER BY first_seen_at DESC"
        ).fetchall()
    finally:
        conn.close()
    paying = [r for r in rows if service.is_paying(r)]
    stepping = [r for r in rows if not service.is_paying(r)]
    return render_template("leads/inbox.html", paying=paying, stepping=stepping)


@bp.route("/leads/excluded")
def excluded():
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT * FROM leads WHERE state = 'excluded' ORDER BY first_seen_at DESC"
        ).fetchall()
    finally:
        conn.close()
    return render_template("leads/excluded.html", leads=rows, reason_chip=REASON_CHIP)


@bp.route("/leads/<int:lead_id>")
def detail(lead_id: int):
    conn = _conn()
    try:
        lead = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    finally:
        conn.close()
    if lead is None:
        abort(404)
    return render_template("leads/detail.html", lead=lead, reason_chip=REASON_CHIP)


@bp.route("/leads/<int:lead_id>", methods=["POST"])
def update(lead_id: int):
    conn = _conn()
    try:
        lead = conn.execute("SELECT id FROM leads WHERE id = ?", (lead_id,)).fetchone()
        if lead is None:
            abort(404)
        fields = {
            "title": (request.form.get("title") or "").strip(),
            "org": (request.form.get("org") or "").strip() or None,
            "location": (request.form.get("location") or "").strip() or None,
            "url": (request.form.get("url") or "").strip() or None,
            "event_date": (request.form.get("event_date") or "").strip() or None,
            "deadline": (request.form.get("deadline") or "").strip() or None,
            "pay_kind": (request.form.get("pay_kind") or "unknown").strip(),
            "pay_min": request.form.get("pay_min") or None,
            "pay_max": request.form.get("pay_max") or None,
            "description": (request.form.get("description") or "").strip(),
        }
        service.update_lead(conn, lead_id, fields)
    finally:
        conn.close()
    return redirect(url_for("leads.detail", lead_id=lead_id))


@bp.route("/leads/<int:lead_id>/restore", methods=["POST"])
def restore(lead_id: int):
    conn = _conn()
    try:
        lead = conn.execute("SELECT id FROM leads WHERE id = ?", (lead_id,)).fetchone()
        if lead is None:
            abort(404)
        service.restore_lead(conn, lead_id)
    finally:
        conn.close()
    return redirect(url_for("leads.excluded"))
