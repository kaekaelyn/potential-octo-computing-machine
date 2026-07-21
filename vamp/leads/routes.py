"""Leads routes: the Paying/Stepping-stones inbox, the Excluded shelf with
one-tap restore, and the finish-by-hand detail/edit view (PLAN.md §4)."""

from __future__ import annotations

import json

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for

from vamp import db as vamp_db
from vamp.ai import degree_review, scoring
from vamp.ai import drafts as drafts_service
from vamp.ai.router import get_provider
from vamp.filters import REASON_CHIP
from vamp.filters.degree import REASON as DEGREE_REASON
from vamp.leads import service
from vamp.money import floor as floor_service
from vamp.vault import matching as vault_matching

bp = Blueprint("leads", __name__)


def _conn():
    config = current_app.config["VAMP_CONFIG"]
    return vamp_db.get_connection(config.db_path)


def _below_floor_ids(conn, rows) -> set[int]:
    floor = floor_service.get_rate_floor(conn)
    if floor is None:
        return set()
    return {
        r["id"]
        for r in rows
        if service.is_paying(r)
        and not r["strategic"]
        and floor_service.is_below_floor(service.pay_amount(r), floor)
    }


@bp.route("/leads")
def inbox():
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT * FROM leads WHERE state != 'excluded' ORDER BY first_seen_at DESC"
        ).fetchall()
        statuses = vault_matching.status_for_leads(conn, [r["id"] for r in rows])
        below_floor = _below_floor_ids(conn, rows)
    finally:
        conn.close()
    paying = [r for r in rows if service.is_paying(r)]
    stepping = [r for r in rows if not service.is_paying(r)]
    return render_template(
        "leads/inbox.html",
        paying=paying,
        stepping=stepping,
        statuses=statuses,
        below_floor=below_floor,
    )


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
        if lead is None:
            abort(404)
        status = vault_matching.lead_status(conn, lead_id)
        score_row = drafts_service.latest_score(conn, lead_id)
        score = None
        if score_row is not None:
            score = {
                "score": score_row["score"],
                "rationale": json.loads(score_row["rationale_json"] or "{}").get("rationale"),
                "flags": json.loads(score_row["rationale_json"] or "{}").get("flags", []),
                "scorer": score_row["scorer"],
                "scored_at": score_row["scored_at"],
            }
        degree_review_row = None
        if lead["state"] == "excluded" and DEGREE_REASON in (lead["excluded_reason"] or ""):
            degree_review_row = drafts_service.latest_draft(
                conn, kind=degree_review.DRAFT_KIND, ref_kind="lead", ref_id=lead_id
            )
        floor = floor_service.get_rate_floor(conn)
        below_floor = (
            service.is_paying(lead)
            and not lead["strategic"]
            and floor_service.is_below_floor(service.pay_amount(lead), floor)
        )
    finally:
        conn.close()
    review = json.loads(degree_review_row["content_json"]) if degree_review_row else None
    return render_template(
        "leads/detail.html",
        lead=lead,
        reason_chip=REASON_CHIP,
        status=status,
        score=score,
        degree_review=review,
        degree_reason=DEGREE_REASON,
        below_floor=below_floor,
    )


@bp.route("/leads/<int:lead_id>/score", methods=["POST"])
def score_now(lead_id: int):
    config = current_app.config["VAMP_CONFIG"]
    conn = _conn()
    try:
        lead = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
        if lead is None:
            abort(404)
        result = scoring.score_lead(conn, get_provider(config), lead)
    finally:
        conn.close()
    if result["provider"] == "none":
        flash("Scored with the heuristic (no AI provider available; see /ai/health).", "info")
    else:
        flash("Scored with Claude.", "info")
    return redirect(url_for("leads.detail", lead_id=lead_id))


@bp.route("/leads/<int:lead_id>/degree-review", methods=["POST"])
def degree_review_now(lead_id: int):
    config = current_app.config["VAMP_CONFIG"]
    conn = _conn()
    try:
        lead = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
        if lead is None:
            abort(404)
        if lead["state"] != "excluded" or DEGREE_REASON not in (lead["excluded_reason"] or ""):
            flash("This lead isn't currently excluded for a degree wall.", "error")
            return redirect(url_for("leads.detail", lead_id=lead_id))
        degree_review.review_lead(conn, get_provider(config), lead)
    finally:
        conn.close()
    flash("Got a second opinion on the degree requirement.", "info")
    return redirect(url_for("leads.detail", lead_id=lead_id))


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
            "strategic": request.form.get("strategic") == "on",
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
