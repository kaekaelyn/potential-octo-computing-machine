"""Vault routes: asset CRUD, the unlock report, the repertoire list
builder, and EPK export (PLAN.md §12 M3)."""

from __future__ import annotations

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from vamp import db as vamp_db
from vamp.requirements.kinds import ASSET_KINDS, ASSET_LABELS
from vamp.vault import assets as assets_service
from vamp.vault import epk as epk_service
from vamp.vault import matching
from vamp.vault import repertoire as repertoire_service

bp = Blueprint("vault", __name__, url_prefix="/vault")


def _conn():
    config = current_app.config["VAMP_CONFIG"]
    return vamp_db.get_connection(config.db_path)


def _vamp_home():
    return current_app.config["VAMP_CONFIG"].home


@bp.route("")
def list_assets():
    conn = _conn()
    try:
        rows = assets_service.list_assets(conn)
    finally:
        conn.close()
    by_kind: dict[str, list] = {kind: [] for kind in ASSET_KINDS}
    for row in rows:
        by_kind.setdefault(row["kind"], []).append(row)
    return render_template(
        "vault/list.html",
        by_kind=by_kind,
        asset_kinds=ASSET_KINDS,
        asset_labels=ASSET_LABELS,
        is_local_file=assets_service.is_local_file,
    )


def _asset_form_fields():
    file = request.files.get("file")
    file_name = file.filename if file and file.filename else None
    file_bytes = file.read() if file_name else None
    return {
        "kind": (request.form.get("kind") or "").strip(),
        "name": (request.form.get("name") or "").strip(),
        "url": (request.form.get("url") or "").strip(),
        "file_name": file_name,
        "file_bytes": file_bytes,
        "tags": (request.form.get("tags") or "").strip(),
        "ready": request.form.get("ready") == "on",
    }


@bp.route("", methods=["POST"])
def create_asset():
    fields = _asset_form_fields()
    if fields["kind"] not in ASSET_KINDS or not fields["name"]:
        flash("An asset needs a kind and a name.", "error")
        return redirect(url_for("vault.list_assets"))
    conn = _conn()
    try:
        assets_service.create_asset(conn, _vamp_home(), **fields)
    finally:
        conn.close()
    flash(f"Added to the vault: {fields['name']}", "info")
    return redirect(url_for("vault.list_assets"))


@bp.route("/<int:asset_id>/edit", methods=["POST"])
def edit_asset(asset_id: int):
    conn = _conn()
    try:
        if assets_service.get_asset(conn, asset_id) is None:
            abort(404)
        fields = _asset_form_fields()
        if fields["kind"] not in ASSET_KINDS or not fields["name"]:
            flash("An asset needs a kind and a name.", "error")
            return redirect(url_for("vault.list_assets"))
        assets_service.update_asset(conn, _vamp_home(), asset_id, **fields)
    finally:
        conn.close()
    return redirect(url_for("vault.list_assets"))


@bp.route("/<int:asset_id>/toggle-ready", methods=["POST"])
def toggle_ready(asset_id: int):
    conn = _conn()
    try:
        if assets_service.get_asset(conn, asset_id) is None:
            abort(404)
        assets_service.toggle_ready(conn, asset_id)
    finally:
        conn.close()
    return redirect(url_for("vault.list_assets"))


@bp.route("/<int:asset_id>/delete", methods=["POST"])
def delete_asset(asset_id: int):
    conn = _conn()
    try:
        if assets_service.get_asset(conn, asset_id) is None:
            abort(404)
        assets_service.delete_asset(conn, asset_id)
    finally:
        conn.close()
    return redirect(url_for("vault.list_assets"))


@bp.route("/unlock")
def unlock_report():
    conn = _conn()
    try:
        report = matching.unlock_report(conn)
    finally:
        conn.close()
    return render_template("vault/unlock.html", report=report)


@bp.route("/repertoire")
def repertoire():
    conn = _conn()
    try:
        items = repertoire_service.list_items(conn)
    finally:
        conn.close()
    return render_template(
        "vault/repertoire.html", items=items, occasions=repertoire_service.OCCASIONS
    )


def _repertoire_form_fields():
    return {
        "title": (request.form.get("title") or "").strip(),
        "artist": (request.form.get("artist") or "").strip(),
        "occasions": request.form.getlist("occasions"),
        "notes": (request.form.get("notes") or "").strip(),
    }


@bp.route("/repertoire", methods=["POST"])
def add_repertoire_item():
    fields = _repertoire_form_fields()
    if not fields["title"]:
        flash("A repertoire item needs a title.", "error")
        return redirect(url_for("vault.repertoire"))
    conn = _conn()
    try:
        repertoire_service.add_item(conn, _vamp_home(), **fields)
    finally:
        conn.close()
    return redirect(url_for("vault.repertoire"))


@bp.route("/repertoire/<int:item_id>/edit", methods=["POST"])
def edit_repertoire_item(item_id: int):
    fields = _repertoire_form_fields()
    conn = _conn()
    try:
        row = conn.execute("SELECT id FROM repertoire_items WHERE id = ?", (item_id,)).fetchone()
        if row is None:
            abort(404)
        repertoire_service.update_item(conn, _vamp_home(), item_id, **fields)
    finally:
        conn.close()
    return redirect(url_for("vault.repertoire"))


@bp.route("/repertoire/<int:item_id>/delete", methods=["POST"])
def delete_repertoire_item(item_id: int):
    conn = _conn()
    try:
        repertoire_service.delete_item(conn, _vamp_home(), item_id)
    finally:
        conn.close()
    return redirect(url_for("vault.repertoire"))


@bp.route("/epk")
def epk_preview():
    conn = _conn()
    try:
        readiness = epk_service.epk_readiness(conn)
    finally:
        conn.close()
    return render_template("vault/epk.html", readiness=readiness)


@bp.route("/epk/download")
def epk_download():
    conn = _conn()
    try:
        out_path = epk_service.export_epk(conn, _vamp_home())
    finally:
        conn.close()
    html_doc = out_path.read_text()
    return Response(
        html_doc,
        mimetype="text/html",
        headers={"Content-Disposition": "attachment; filename=epk.html"},
    )
