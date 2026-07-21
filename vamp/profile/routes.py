"""Profile settings page: display name, instrument, home area, and the
voice-sample text AI drafting reads from (PLAN.md §9)."""

from __future__ import annotations

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for

from vamp import db as vamp_db
from vamp.profile import service as profile_service

bp = Blueprint("profile", __name__, url_prefix="/profile")


def _conn():
    config = current_app.config["VAMP_CONFIG"]
    return vamp_db.get_connection(config.db_path)


@bp.route("")
def edit():
    conn = _conn()
    try:
        profile = profile_service.get_profile(conn)
    finally:
        conn.close()
    return render_template("profile/edit.html", profile=profile)


@bp.route("", methods=["POST"])
def update():
    values = {
        "display_name": (request.form.get("display_name") or "").strip(),
        "instrument": (request.form.get("instrument") or "").strip(),
        "home_area": (request.form.get("home_area") or "").strip(),
        "voice_sample": (request.form.get("voice_sample") or "").strip(),
    }
    conn = _conn()
    try:
        profile_service.set_profile(conn, values)
    finally:
        conn.close()
    flash("Profile saved.", "info")
    return redirect(url_for("profile.edit"))
