"""Playbook routes: list the seven strategies and render one, alongside the
prospects and scene events seeded to execute it (PLAN.md §6)."""

from __future__ import annotations

from datetime import UTC, datetime

from flask import Blueprint, abort, current_app, render_template
from markupsafe import Markup

from vamp import db as vamp_db
from vamp.playbooks.activation import active_months_list
from vamp.playbooks.render import render_markdown

bp = Blueprint("playbooks", __name__, url_prefix="/playbooks")

_MONTH_NAMES = {
    1: "Jan",
    2: "Feb",
    3: "Mar",
    4: "Apr",
    5: "May",
    6: "Jun",
    7: "Jul",
    8: "Aug",
    9: "Sep",
    10: "Oct",
    11: "Nov",
    12: "Dec",
}


def _conn():
    config = current_app.config["VAMP_CONFIG"]
    return vamp_db.get_connection(config.db_path)


@bp.route("")
def list_playbooks():
    conn = _conn()
    try:
        rows = conn.execute("SELECT * FROM playbooks ORDER BY id").fetchall()
        counts = {
            row["playbook"]: row["n"]
            for row in conn.execute(
                "SELECT playbook, COUNT(*) AS n FROM prospects "
                "WHERE playbook IS NOT NULL GROUP BY playbook"
            ).fetchall()
        }
    finally:
        conn.close()
    this_month = datetime.now(UTC).month
    playbooks = []
    for row in rows:
        months = active_months_list(row["active_months"])
        playbooks.append(
            {
                "slug": row["slug"],
                "title": row["title"],
                "months": [_MONTH_NAMES[m] for m in months],
                "active_now": this_month in months if months else False,
                "prospect_count": counts.get(row["slug"], 0),
            }
        )
    return render_template("playbooks/list.html", playbooks=playbooks)


@bp.route("/<slug>")
def detail(slug: str):
    conn = _conn()
    try:
        row = conn.execute("SELECT * FROM playbooks WHERE slug = ?", (slug,)).fetchone()
        if row is None:
            abort(404)
        prospects = conn.execute(
            "SELECT id, name, category, area, status, verified FROM prospects "
            "WHERE playbook = ? ORDER BY name COLLATE NOCASE",
            (slug,),
        ).fetchall()
        scene_events = conn.execute(
            "SELECT id, name, venue, area, kind FROM scene_events "
            "WHERE playbook = ? ORDER BY name COLLATE NOCASE",
            (slug,),
        ).fetchall()
    finally:
        conn.close()
    months = [_MONTH_NAMES[m] for m in active_months_list(row["active_months"])]
    return render_template(
        "playbooks/detail.html",
        playbook=row,
        body_html=Markup(render_markdown(row["body_md"] or "")),
        months=months,
        prospects=prospects,
        scene_events=scene_events,
    )
