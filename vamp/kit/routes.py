from __future__ import annotations

from flask import Blueprint, abort, current_app, redirect, render_template, request, url_for

from vamp import db as vamp_db
from vamp.vault.kit import list_kit_tasks, set_kit_task_state

bp = Blueprint("kit", __name__, url_prefix="/kit")


def _conn():
    config = current_app.config["VAMP_CONFIG"]
    return vamp_db.get_connection(config.db_path)


@bp.route("")
def checklist():
    conn = _conn()
    try:
        tasks = list_kit_tasks(conn)
        vault_ready_kinds = {
            row["kind"] for row in conn.execute("SELECT DISTINCT kind FROM assets WHERE ready = 1")
        }
    finally:
        conn.close()
    done = sum(1 for t in tasks if t["state"] == "done")
    return render_template(
        "kit/checklist.html",
        tasks=tasks,
        vault_ready_kinds=vault_ready_kinds,
        done=done,
        total=len(tasks),
    )


@bp.route("/<int:task_id>/toggle", methods=["POST"])
def toggle(task_id: int):
    conn = _conn()
    try:
        row = conn.execute("SELECT state FROM kit_tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            abort(404)
        new_state = "todo" if row["state"] == "done" else "done"
        set_kit_task_state(conn, task_id, new_state)
    finally:
        conn.close()
    return redirect(request.referrer or url_for("kit.checklist"))
