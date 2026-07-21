"""Notification status page (PLAN.md §7/§9/§12 M7): whether
``termux-notification`` is actually available, and manual "send now"
triggers for the morning digest and Outreach Sprint so both can be
demoed/tested without waiting for the scheduled hour."""

from __future__ import annotations

import shutil

from flask import Blueprint, current_app, flash, redirect, render_template, url_for

from vamp import db as vamp_db
from vamp.notify import jobs as notify_jobs

bp = Blueprint("notify", __name__, url_prefix="/notify")


def _conn():
    config = current_app.config["VAMP_CONFIG"]
    return vamp_db.get_connection(config.db_path)


def _last_event(conn, kind_prefix: str):
    return conn.execute(
        "SELECT * FROM events WHERE kind LIKE ? ORDER BY id DESC LIMIT 1", (f"{kind_prefix}:%",)
    ).fetchone()


@bp.route("")
def status():
    available = shutil.which("termux-notification") is not None
    conn = _conn()
    try:
        last_digest = _last_event(conn, notify_jobs.MORNING_DIGEST_KIND)
        last_sprint = _last_event(conn, notify_jobs.SPRINT_KIND)
    finally:
        conn.close()
    return render_template(
        "notify/status.html", available=available, last_digest=last_digest, last_sprint=last_sprint
    )


def _flash_result(result: dict, *, ok_noun: str) -> None:
    if result.get("skipped"):
        flash(f"{ok_noun} not sent: {result['reason']}", "error")
        return
    status = result["notify"].status
    flash(
        f"{ok_noun} sent ({status}): {result['headline']}", "info" if status != "error" else "error"
    )


@bp.route("/digest/send", methods=["POST"])
def send_digest_now():
    config = current_app.config["VAMP_CONFIG"]
    conn = _conn()
    try:
        result = notify_jobs.send_morning_digest(conn, config, force=True)
    finally:
        conn.close()
    _flash_result(result, ok_noun="Digest")
    return redirect(url_for("notify.status"))


@bp.route("/sprint/send", methods=["POST"])
def send_sprint_now():
    config = current_app.config["VAMP_CONFIG"]
    conn = _conn()
    try:
        result = notify_jobs.send_sunday_sprint(conn, config, force=True)
    finally:
        conn.close()
    _flash_result(result, ok_noun="Outreach Sprint")
    return redirect(url_for("notify.status"))
