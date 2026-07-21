"""Metrics page route (PLAN.md §7/§12 M7)."""

from __future__ import annotations

from flask import Blueprint, current_app, render_template

from vamp import db as vamp_db
from vamp.metrics import service

bp = Blueprint("metrics", __name__, url_prefix="/metrics")


def _conn():
    config = current_app.config["VAMP_CONFIG"]
    return vamp_db.get_connection(config.db_path)


@bp.route("")
def dashboard():
    conn = _conn()
    try:
        data = service.dashboard(conn)
    finally:
        conn.close()
    return render_template("metrics/dashboard.html", data=data)
