"""Scene calendar routes: CRUD, going toggle, and the post-event "met
anyone?" recap flow linking into the people log (PLAN.md §7/§12 M6)."""

from __future__ import annotations

import json

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for

from vamp import db as vamp_db
from vamp.people import service as people_service
from vamp.scene import cadence as cadence_engine
from vamp.scene import service

bp = Blueprint("scene", __name__, url_prefix="/scene")


def _conn():
    config = current_app.config["VAMP_CONFIG"]
    return vamp_db.get_connection(config.db_path)


def _cadence_from_form() -> dict | None:
    freq = (request.form.get("cadence_freq") or "").strip().lower()
    if not freq:
        return None
    cadence: dict = {"freq": freq}
    weekday = (request.form.get("cadence_weekday") or "").strip().lower()
    if weekday:
        cadence["weekday"] = weekday
    week = (request.form.get("cadence_week") or "").strip()
    if week:
        cadence["week"] = int(week)
    month = (request.form.get("cadence_month") or "").strip()
    if month:
        cadence["month"] = int(month)
    day = (request.form.get("cadence_day") or "").strip()
    if day:
        cadence["day"] = int(day)
    return cadence


def _form_fields() -> dict:
    return {
        "name": (request.form.get("name") or "").strip(),
        "venue": (request.form.get("venue") or "").strip() or None,
        "area": (request.form.get("area") or "").strip() or None,
        "url": (request.form.get("url") or "").strip() or None,
        "kind": (request.form.get("kind") or "").strip() or None,
        "notes": (request.form.get("notes") or "").strip() or None,
        "playbook": (request.form.get("playbook") or "").strip() or None,
    }


@bp.route("")
def list_events():
    conn = _conn()
    try:
        service.sync_recap_reminders(conn)
        rows = service.list_events(conn)
        recaps = {
            r["ref_id"]: r
            for r in conn.execute(
                "SELECT * FROM reminders WHERE ref_kind = ? AND done = 0",
                (service.RECAP_REF_KIND,),
            ).fetchall()
        }
    finally:
        conn.close()
    events = []
    for row in rows:
        cadence = json.loads(row["cadence_json"]) if row["cadence_json"] else None
        events.append(
            {
                "row": row,
                "cadence_label": cadence_engine.describe_cadence(cadence),
                "next_occurrence": cadence_engine.next_occurrence(cadence),
                "recap": recaps.get(row["id"]),
            }
        )
    return render_template("scene/list.html", events=events)


@bp.route("", methods=["POST"])
def create():
    fields = _form_fields()
    if not fields["name"]:
        flash("A scene event needs a name.", "error")
        return redirect(url_for("scene.list_events"))
    conn = _conn()
    try:
        service.create_event(conn, fields, _cadence_from_form())
    finally:
        conn.close()
    flash(f"Added: {fields['name']}", "info")
    return redirect(url_for("scene.list_events"))


@bp.route("/<int:event_id>/edit", methods=["POST"])
def edit(event_id: int):
    conn = _conn()
    try:
        if service.get_event(conn, event_id) is None:
            abort(404)
        fields = _form_fields()
        if not fields["name"]:
            flash("A scene event needs a name.", "error")
            return redirect(url_for("scene.list_events"))
        service.update_event(conn, event_id, fields, _cadence_from_form())
    finally:
        conn.close()
    return redirect(url_for("scene.list_events"))


@bp.route("/<int:event_id>/going", methods=["POST"])
def toggle_going(event_id: int):
    conn = _conn()
    try:
        if service.get_event(conn, event_id) is None:
            abort(404)
        service.toggle_going(conn, event_id)
    finally:
        conn.close()
    return redirect(url_for("scene.list_events"))


@bp.route("/<int:event_id>/delete", methods=["POST"])
def delete(event_id: int):
    conn = _conn()
    try:
        if service.get_event(conn, event_id) is None:
            abort(404)
        service.delete_event(conn, event_id)
    finally:
        conn.close()
    return redirect(url_for("scene.list_events"))


@bp.route("/<int:event_id>/recap", methods=["POST"])
def recap(event_id: int):
    person_id = None
    name = (request.form.get("person_name") or "").strip()
    conn = _conn()
    try:
        row = service.get_event(conn, event_id)
        if row is None:
            abort(404)
        if name:
            reminder = service.open_recap_reminder(conn, event_id)
            met_at = row["name"]
            if reminder is not None:
                met_at = f"{row['name']} ({reminder['due_at'][:10]})"
            person_id = people_service.create_person(
                conn,
                {
                    "name": name,
                    "role": (request.form.get("person_role") or "").strip() or None,
                    "org": (request.form.get("person_org") or "").strip() or None,
                    "met_at": met_at,
                    "notes": (request.form.get("person_notes") or "").strip() or None,
                },
            )
        service.dismiss_recap(conn, event_id)
    finally:
        conn.close()
    if person_id is not None:
        flash("Person added to the log.", "info")
        return redirect(url_for("people.detail", person_id=person_id))
    flash("Noted — no one new this time.", "info")
    return redirect(url_for("scene.list_events"))
