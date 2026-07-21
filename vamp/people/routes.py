"""People routes: the log + referral chain (person → gig), PLAN.md §7/§12 M6."""

from __future__ import annotations

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for

from vamp import db as vamp_db
from vamp.gigs import pipeline as gigs_pipeline
from vamp.people import service

bp = Blueprint("people", __name__, url_prefix="/people")


def _conn():
    config = current_app.config["VAMP_CONFIG"]
    return vamp_db.get_connection(config.db_path)


def _form_fields() -> dict:
    return {
        "name": (request.form.get("name") or "").strip(),
        "role": (request.form.get("role") or "").strip() or None,
        "org": (request.form.get("org") or "").strip() or None,
        "met_at": (request.form.get("met_at") or "").strip() or None,
        "phone": (request.form.get("phone") or "").strip() or None,
        "email": (request.form.get("email") or "").strip() or None,
        "notes": (request.form.get("notes") or "").strip() or None,
    }


@bp.route("")
def list_people():
    conn = _conn()
    try:
        people = service.list_people(conn)
        referral_counts = {
            row["person_id"]: row["n"]
            for row in conn.execute(
                "SELECT person_id, COUNT(*) AS n FROM referrals GROUP BY person_id"
            ).fetchall()
        }
    finally:
        conn.close()
    return render_template("people/list.html", people=people, referral_counts=referral_counts)


@bp.route("", methods=["POST"])
def create():
    fields = _form_fields()
    if not fields["name"]:
        flash("A person needs at least a name.", "error")
        return redirect(url_for("people.list_people"))
    conn = _conn()
    try:
        person_id = service.create_person(conn, fields)
    finally:
        conn.close()
    return redirect(url_for("people.detail", person_id=person_id))


@bp.route("/<int:person_id>")
def detail(person_id: int):
    conn = _conn()
    try:
        person = service.get_person(conn, person_id)
        if person is None:
            abort(404)
        referrals = service.referrals_for_person(conn, person_id)
        gigs = gigs_pipeline.list_gigs(conn)
    finally:
        conn.close()
    return render_template(
        "people/detail.html",
        person=person,
        contact=service.contact_fields(person),
        referrals=referrals,
        gigs=gigs,
    )


@bp.route("/<int:person_id>/edit", methods=["POST"])
def edit(person_id: int):
    conn = _conn()
    try:
        if service.get_person(conn, person_id) is None:
            abort(404)
        fields = _form_fields()
        if not fields["name"]:
            flash("A person needs at least a name.", "error")
            return redirect(url_for("people.detail", person_id=person_id))
        service.update_person(conn, person_id, fields)
    finally:
        conn.close()
    flash("Person updated.", "info")
    return redirect(url_for("people.detail", person_id=person_id))


@bp.route("/<int:person_id>/delete", methods=["POST"])
def delete(person_id: int):
    conn = _conn()
    try:
        if service.get_person(conn, person_id) is None:
            abort(404)
        service.delete_person(conn, person_id)
    finally:
        conn.close()
    flash("Person removed.", "info")
    return redirect(url_for("people.list_people"))


@bp.route("/<int:person_id>/referral", methods=["POST"])
def add_referral(person_id: int):
    gig_id = request.form.get("gig_id", type=int)
    conn = _conn()
    try:
        if service.get_person(conn, person_id) is None:
            abort(404)
        if gig_id is None or gigs_pipeline.get_gig(conn, gig_id) is None:
            flash("Pick a real gig to credit this referral to.", "error")
            return redirect(url_for("people.detail", person_id=person_id))
        service.add_referral(conn, person_id, gig_id)
    finally:
        conn.close()
    flash("Referral logged.", "info")
    return redirect(url_for("people.detail", person_id=person_id))


@bp.route("/referral/<int:referral_id>/delete", methods=["POST"])
def delete_referral(referral_id: int):
    person_id = request.form.get("person_id", type=int)
    conn = _conn()
    try:
        service.remove_referral(conn, referral_id)
    finally:
        conn.close()
    if person_id:
        return redirect(url_for("people.detail", person_id=person_id))
    return redirect(url_for("people.list_people"))
