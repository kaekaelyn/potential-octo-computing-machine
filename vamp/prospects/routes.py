"""Prospect routes: the pipeline board, a prospect's detail + touches log,
status transitions, the weekly Outreach Sprint, and the Overpass importer
trigger (PLAN.md §6/§12 M4)."""

from __future__ import annotations

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from vamp import db as vamp_db
from vamp.prospects import cadence, pipeline
from vamp.prospects.overpass import CATEGORY_QUERIES, OverpassImporter

bp = Blueprint("prospects", __name__, url_prefix="/prospects")


def _conn():
    config = current_app.config["VAMP_CONFIG"]
    return vamp_db.get_connection(config.db_path)


def _form_fields() -> dict:
    return {
        "name": (request.form.get("name") or "").strip(),
        "category": (request.form.get("category") or "").strip(),
        "area": (request.form.get("area") or "").strip() or None,
        "address": (request.form.get("address") or "").strip() or None,
        "phone": (request.form.get("phone") or "").strip() or None,
        "email": (request.form.get("email") or "").strip() or None,
        "website": (request.form.get("website") or "").strip() or None,
        "has_piano": request.form.get("has_piano") or None,
        "angle": (request.form.get("angle") or "").strip() or None,
        "source": (request.form.get("source") or "").strip() or None,
        "verified": 1 if request.form.get("verified") == "on" else 0,
        "notes": (request.form.get("notes") or "").strip() or None,
        "cooldown_days": (request.form.get("cooldown_days") or "").strip() or None,
        "playbook": (request.form.get("playbook") or "").strip() or None,
        "status": (request.form.get("status") or "").strip() or None,
    }


@bp.route("")
def board():
    status = request.args.get("status") or None
    category = request.args.get("category") or None
    conn = _conn()
    try:
        rows = pipeline.list_prospects(conn, status=status, category=category)
        cat_counts = pipeline.category_counts(conn)
        status_counts = conn.execute(
            "SELECT status, COUNT(*) AS n FROM prospects GROUP BY status"
        ).fetchall()
    finally:
        conn.close()
    now = cadence.naive_utc_now()
    prospects = [{"row": r, "cooldown": cadence.in_cooldown(r, now)} for r in rows]
    return render_template(
        "prospects/board.html",
        prospects=prospects,
        states=pipeline.PIPELINE_STATES,
        state_labels=pipeline.STATE_LABELS,
        status_counts={r["status"]: r["n"] for r in status_counts},
        category_counts=cat_counts,
        active_status=status,
        active_category=category,
        categories=sorted(CATEGORY_QUERIES.keys()),
    )


@bp.route("", methods=["POST"])
def create():
    fields = _form_fields()
    if not fields["name"] or not fields["category"]:
        flash("A prospect needs at least a name and a category.", "error")
        return redirect(url_for("prospects.board"))
    conn = _conn()
    try:
        prospect_id = pipeline.create_prospect(conn, fields)
    finally:
        conn.close()
    flash(f"Added prospect: {fields['name']}", "info")
    return redirect(url_for("prospects.detail", prospect_id=prospect_id))


@bp.route("/<int:prospect_id>")
def detail(prospect_id: int):
    conn = _conn()
    try:
        row = pipeline.get_prospect(conn, prospect_id)
        if row is None:
            abort(404)
        touches = pipeline.prospect_touches(conn, prospect_id)
        follow_ups = conn.execute(
            "SELECT * FROM reminders WHERE ref_kind = ? AND ref_id = ? ORDER BY done, due_at",
            (cadence.FOLLOW_UP_REF_KIND, prospect_id),
        ).fetchall()
        playbook_row = None
        if row["playbook"]:
            playbook_row = conn.execute(
                "SELECT slug, title FROM playbooks WHERE slug = ?", (row["playbook"],)
            ).fetchone()
    finally:
        conn.close()
    return render_template(
        "prospects/detail.html",
        p=row,
        touches=touches,
        follow_ups=follow_ups,
        playbook=playbook_row,
        in_cooldown=cadence.in_cooldown(row),
        cooldown_days=cadence.cooldown_days_for(row),
        states=pipeline.PIPELINE_STATES,
        state_labels=pipeline.STATE_LABELS,
        next_state=pipeline.next_state(row["status"]),
    )


@bp.route("/<int:prospect_id>/edit", methods=["POST"])
def edit(prospect_id: int):
    conn = _conn()
    try:
        if pipeline.get_prospect(conn, prospect_id) is None:
            abort(404)
        fields = _form_fields()
        if not fields["name"] or not fields["category"]:
            flash("A prospect needs at least a name and a category.", "error")
            return redirect(url_for("prospects.detail", prospect_id=prospect_id))
        pipeline.update_prospect(conn, prospect_id, fields)
    finally:
        conn.close()
    flash("Prospect updated.", "info")
    return redirect(url_for("prospects.detail", prospect_id=prospect_id))


@bp.route("/<int:prospect_id>/status", methods=["POST"])
def set_status(prospect_id: int):
    new_status = (request.form.get("status") or "").strip()
    conn = _conn()
    try:
        if pipeline.get_prospect(conn, prospect_id) is None:
            abort(404)
        if new_status not in pipeline.PIPELINE_STATES:
            flash("Unknown status.", "error")
            return redirect(url_for("prospects.detail", prospect_id=prospect_id))
        pipeline.set_status(conn, prospect_id, new_status)
    finally:
        conn.close()
    return redirect(url_for("prospects.detail", prospect_id=prospect_id))


@bp.route("/<int:prospect_id>/advance", methods=["POST"])
def advance(prospect_id: int):
    conn = _conn()
    try:
        if pipeline.get_prospect(conn, prospect_id) is None:
            abort(404)
        pipeline.advance_status(conn, prospect_id)
    finally:
        conn.close()
    return redirect(url_for("prospects.detail", prospect_id=prospect_id))


@bp.route("/<int:prospect_id>/touch", methods=["POST"])
def touch(prospect_id: int):
    channel = (request.form.get("channel") or "").strip() or None
    summary = (request.form.get("summary") or "").strip() or None
    outcome = (request.form.get("outcome") or "").strip() or None
    schedule = request.form.get("schedule_follow_ups") != "off"
    conn = _conn()
    try:
        if pipeline.get_prospect(conn, prospect_id) is None:
            abort(404)
        pipeline.log_touch(
            conn,
            prospect_id,
            channel=channel,
            summary=summary,
            outcome=outcome,
            schedule_follow_ups=schedule,
        )
    finally:
        conn.close()
    if schedule:
        flash("Touch logged; follow-ups scheduled for +7d and +21d.", "info")
    else:
        flash("Touch logged.", "info")
    return redirect(url_for("prospects.detail", prospect_id=prospect_id))


@bp.route("/<int:prospect_id>/delete", methods=["POST"])
def delete(prospect_id: int):
    conn = _conn()
    try:
        if pipeline.get_prospect(conn, prospect_id) is None:
            abort(404)
        pipeline.delete_prospect(conn, prospect_id)
    finally:
        conn.close()
    flash("Prospect removed.", "info")
    return redirect(url_for("prospects.board"))


@bp.route("/sprint")
def sprint():
    conn = _conn()
    try:
        data = cadence.outreach_sprint(conn)
    finally:
        conn.close()
    return render_template(
        "prospects/sprint.html", sprint=data, headline=cadence.sprint_headline(data)
    )


@bp.route("/import", methods=["GET"])
def import_form():
    return render_template("prospects/import.html", categories=sorted(CATEGORY_QUERIES.keys()))


@bp.route("/import", methods=["POST"])
def run_import():
    categories = request.form.getlist("categories")
    categories = [c for c in categories if c in CATEGORY_QUERIES]
    if not categories:
        flash("Pick at least one category to import.", "error")
        return redirect(url_for("prospects.import_form"))
    conn = _conn()
    try:
        importer = OverpassImporter(conn)
        results = importer.import_categories(categories)
    finally:
        conn.close()
    imported = sum(r["imported"] for r in results)
    failed = [r["category"] for r in results if not r["ok"]]
    flash(
        f"Imported {imported} new prospect(s) as unverified from OpenStreetMap."
        + (f" Failed: {', '.join(failed)}." if failed else ""),
        "info" if imported or not failed else "error",
    )
    return redirect(url_for("prospects.board", status="identified"))
