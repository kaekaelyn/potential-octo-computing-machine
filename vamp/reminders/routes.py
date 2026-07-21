"""Consolidated reminders page (PLAN.md §7/§12 M6): prospect follow-ups
(M4), gig chase-unpaid reminders, and scene-event "met anyone?" recap
prompts (both M6), all surfaced in one place instead of needing their own
page to be noticed."""

from __future__ import annotations

from flask import Blueprint, current_app, redirect, render_template, url_for

from vamp import db as vamp_db
from vamp.gigs.pipeline import CHASE_UNPAID_REF_KIND
from vamp.prospects.cadence import FOLLOW_UP_REF_KIND, naive_utc_now
from vamp.scene.service import RECAP_REF_KIND, sync_recap_reminders

bp = Blueprint("reminders", __name__, url_prefix="/reminders")


def _conn():
    config = current_app.config["VAMP_CONFIG"]
    return vamp_db.get_connection(config.db_path)


def _describe(conn, row) -> dict | None:
    """Friendly label + link for one reminder row, resolved by ref_kind.
    None means the thing it pointed at is gone (deleted prospect/gig/event)
    — skip it rather than show a dead link."""
    ref_kind, ref_id = row["ref_kind"], row["ref_id"]
    if ref_kind == FOLLOW_UP_REF_KIND:
        prospect = conn.execute("SELECT id, name FROM prospects WHERE id = ?", (ref_id,)).fetchone()
        if prospect is None:
            return None
        return {
            "label": f"Follow up: {prospect['name']}",
            "link": url_for("prospects.detail", prospect_id=prospect["id"]),
        }
    if ref_kind == CHASE_UNPAID_REF_KIND:
        gig = conn.execute("SELECT id, venue, date FROM gigs WHERE id = ?", (ref_id,)).fetchone()
        if gig is None:
            return None
        return {
            "label": f"Chase unpaid: {gig['venue'] or 'gig'} ({gig['date'] or 'date TBD'})",
            "link": url_for("gigs.detail", gig_id=gig["id"]),
        }
    if ref_kind == RECAP_REF_KIND:
        event = conn.execute("SELECT id, name FROM scene_events WHERE id = ?", (ref_id,)).fetchone()
        if event is None:
            return None
        return {"label": f"Met anyone at {event['name']}?", "link": url_for("scene.list_events")}
    return {"label": row["message"] or ref_kind, "link": None}


@bp.route("")
def list_reminders():
    conn = _conn()
    try:
        sync_recap_reminders(conn)
        rows = conn.execute("SELECT * FROM reminders WHERE done = 0 ORDER BY due_at ASC").fetchall()
        items = []
        for row in rows:
            described = _describe(conn, row)
            if described is None:
                continue
            items.append({"row": row, **described})
    finally:
        conn.close()
    now = naive_utc_now().strftime("%Y-%m-%d %H:%M:%S")
    return render_template("reminders/list.html", items=items, now=now)


@bp.route("/<int:reminder_id>/done", methods=["POST"])
def mark_done(reminder_id: int):
    conn = _conn()
    try:
        conn.execute("UPDATE reminders SET done = 1 WHERE id = ?", (reminder_id,))
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for("reminders.list_reminders"))
