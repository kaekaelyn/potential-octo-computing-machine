"""Capture routes: the Android share-target endpoint and the paste-a-URL
/paste-text UI (PLAN.md §3)."""

from __future__ import annotations

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for

from vamp import db as vamp_db
from vamp.capture.parser import capture as run_capture
from vamp.leads import service

bp = Blueprint("capture", __name__)


def _conn():
    config = current_app.config["VAMP_CONFIG"]
    return vamp_db.get_connection(config.db_path)


def _capture_and_redirect(url: str | None, text: str | None, title: str | None):
    parsed = run_capture(url=url, text=text, title=title)
    conn = _conn()
    try:
        lead_id, created, _existing = service.create_lead(conn, parsed)
    finally:
        conn.close()
    if not created:
        flash("Already captured — this is the existing lead.", "info")
    elif parsed.needs_review:
        flash("Captured. Fetch didn't work, so finish this one by hand.", "info")
    else:
        flash("Captured.", "info")
    return redirect(url_for("leads.detail", lead_id=lead_id))


@bp.route("/capture", methods=["GET"])
def form():
    return render_template("capture/form.html")


@bp.route("/capture", methods=["POST"])
def submit():
    url = (request.form.get("url") or "").strip() or None
    text = (request.form.get("text") or "").strip() or None
    if not url and not text:
        flash("Paste a URL or some text to capture.", "error")
        return redirect(url_for("capture.form"))
    return _capture_and_redirect(url=url, text=text, title=None)


@bp.route("/capture/share", methods=["POST"])
def share_target():
    """Android Web Share Target (see manifest.webmanifest's share_target)."""
    title = (request.form.get("title") or "").strip() or None
    text = (request.form.get("text") or "").strip() or None
    url = (request.form.get("url") or "").strip() or None
    return _capture_and_redirect(url=url, text=text, title=title)
