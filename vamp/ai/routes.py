"""The AI health panel (PLAN.md §9/§12 M5): "Claude: logged in ✓" or
Termux fix instructions, plus a manual "run nightly now" button so the
batch job doesn't have to be demoed by waiting for 3am."""

from __future__ import annotations

from flask import Blueprint, current_app, flash, redirect, render_template, url_for

from vamp import db as vamp_db
from vamp.ai import health_cache
from vamp.ai.batch import run_nightly
from vamp.ai.health import TERMUX_FIX_STEPS

bp = Blueprint("ai", __name__, url_prefix="/ai")


def _conn():
    config = current_app.config["VAMP_CONFIG"]
    return vamp_db.get_connection(config.db_path)


@bp.route("/health")
def health():
    conn = _conn()
    try:
        status, checked_at = health_cache.get_cached_health(conn)
    finally:
        conn.close()
    return render_template(
        "ai/health.html", status=status, checked_at=checked_at, fix_steps=TERMUX_FIX_STEPS
    )


@bp.route("/health/check", methods=["POST"])
def check_now():
    conn = _conn()
    try:
        status = health_cache.refresh_health(conn)
    finally:
        conn.close()
    flash(status.label, "info" if status.ok else "error")
    return redirect(url_for("ai.health"))


@bp.route("/nightly/run", methods=["POST"])
def run_nightly_now():
    """Manual trigger for the nightly batch — mirrors the scheduled 3am job
    (``vamp.ai.scheduler``) so it can be demoed/tested without waiting."""
    config = current_app.config["VAMP_CONFIG"]
    conn = _conn()
    try:
        summary = run_nightly(conn, config)
    finally:
        conn.close()
    flash(
        f"Nightly AI run: {summary['scored']} scored, "
        f"{summary['degree_reviewed']} degree reviews ({summary['degree_overridden']} overridden), "
        f"{summary['requirements_added']} requirements added.",
        "info",
    )
    return redirect(url_for("ai.health"))
