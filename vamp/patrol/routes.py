"""Patrol checklist: CRUD + last-checked ticks for the daily manual skim
of FB groups/pages Vamp is not allowed to automate (PLAN.md §3)."""

from __future__ import annotations

from datetime import UTC, datetime

from flask import Blueprint, abort, current_app, redirect, render_template, request, url_for

from vamp import db as vamp_db

bp = Blueprint("patrol", __name__)


def _conn():
    config = current_app.config["VAMP_CONFIG"]
    return vamp_db.get_connection(config.db_path)


@bp.route("/patrol")
def list_items():
    conn = _conn()
    try:
        rows = conn.execute("SELECT * FROM patrol_items ORDER BY name COLLATE NOCASE").fetchall()
    finally:
        conn.close()
    today = datetime.now(UTC).date().isoformat()
    return render_template("patrol/list.html", items=rows, today=today)


@bp.route("/patrol", methods=["POST"])
def create_item():
    name = (request.form.get("name") or "").strip()
    if name:
        url = (request.form.get("url") or "").strip() or None
        notes = (request.form.get("notes") or "").strip()
        conn = _conn()
        try:
            conn.execute(
                "INSERT INTO patrol_items (name, url, notes) VALUES (?, ?, ?)", (name, url, notes)
            )
            conn.commit()
        finally:
            conn.close()
    return redirect(url_for("patrol.list_items"))


@bp.route("/patrol/<int:item_id>/edit", methods=["POST"])
def edit_item(item_id: int):
    conn = _conn()
    try:
        item = conn.execute("SELECT id FROM patrol_items WHERE id = ?", (item_id,)).fetchone()
        if item is None:
            abort(404)
        conn.execute(
            "UPDATE patrol_items SET name = ?, url = ?, notes = ? WHERE id = ?",
            (
                (request.form.get("name") or "").strip(),
                (request.form.get("url") or "").strip() or None,
                (request.form.get("notes") or "").strip(),
                item_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for("patrol.list_items"))


@bp.route("/patrol/<int:item_id>/check", methods=["POST"])
def check_item(item_id: int):
    conn = _conn()
    try:
        item = conn.execute("SELECT id FROM patrol_items WHERE id = ?", (item_id,)).fetchone()
        if item is None:
            abort(404)
        conn.execute(
            "UPDATE patrol_items SET last_checked_at = datetime('now') WHERE id = ?", (item_id,)
        )
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for("patrol.list_items"))


@bp.route("/patrol/<int:item_id>/delete", methods=["POST"])
def delete_item(item_id: int):
    conn = _conn()
    try:
        conn.execute("DELETE FROM patrol_items WHERE id = ?", (item_id,))
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for("patrol.list_items"))
