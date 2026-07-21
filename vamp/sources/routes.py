"""/sources admin page: enable/disable adapters, see last fetch/last error,
and add RSS feeds or page-watch targets (PLAN.md §12 M2)."""

from __future__ import annotations

import json

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for

from vamp import db as vamp_db
from vamp.sources.page_watcher import PageWatchConfig

bp = Blueprint("sources", __name__)

DEFAULT_RSS_INTERVAL_HOURS = 4
DEFAULT_PAGE_WATCH_INTERVAL_HOURS = 24


def _conn():
    config = current_app.config["VAMP_CONFIG"]
    return vamp_db.get_connection(config.db_path)


def _parse_hours(raw: str | None, default_hours: float) -> float:
    try:
        return float(raw) if raw else default_hours
    except ValueError:
        return default_hours


@bp.route("/sources")
def list_sources():
    conn = _conn()
    try:
        rows = conn.execute("SELECT * FROM sources ORDER BY kind, name").fetchall()
    finally:
        conn.close()
    return render_template("sources/list.html", sources=rows)


@bp.route("/sources/<int:source_id>/toggle", methods=["POST"])
def toggle(source_id: int):
    conn = _conn()
    try:
        row = conn.execute("SELECT enabled FROM sources WHERE id = ?", (source_id,)).fetchone()
        if row is None:
            abort(404)
        conn.execute(
            "UPDATE sources SET enabled = ? WHERE id = ?",
            (0 if row["enabled"] else 1, source_id),
        )
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for("sources.list_sources"))


@bp.route("/sources/add-rss", methods=["POST"])
def add_rss():
    name = (request.form.get("name") or "").strip()
    feed_url = (request.form.get("feed_url") or "").strip()
    if not name or not feed_url:
        flash("An RSS source needs a name and a feed URL.", "error")
        return redirect(url_for("sources.list_sources"))

    interval_seconds = max(
        300,
        int(_parse_hours(request.form.get("interval_hours"), DEFAULT_RSS_INTERVAL_HOURS) * 3600),
    )
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO sources (kind, name, config_json, enabled, interval_seconds) "
            "VALUES ('rss', ?, ?, 1, ?)",
            (name, json.dumps({"feed_url": feed_url}), interval_seconds),
        )
        conn.commit()
    finally:
        conn.close()
    flash(f"Added RSS source: {name}", "info")
    return redirect(url_for("sources.list_sources"))


@bp.route("/sources/add-page-watch", methods=["POST"])
def add_page_watch():
    name = (request.form.get("name") or "").strip()
    url = (request.form.get("url") or "").strip()
    mode = (request.form.get("mode") or "diff").strip()
    selector = (request.form.get("selector") or "").strip() or None
    interval_seconds = int(
        _parse_hours(request.form.get("interval_hours"), DEFAULT_PAGE_WATCH_INTERVAL_HOURS) * 3600
    )

    try:
        PageWatchConfig(
            url=url,
            name=name or url,
            mode=mode,
            selector=selector,
            interval_seconds=interval_seconds,
        )
    except Exception as exc:
        flash(f"Couldn't add page watcher: {exc}", "error")
        return redirect(url_for("sources.list_sources"))

    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO sources (kind, name, config_json, enabled, interval_seconds) "
            "VALUES ('page_watch', ?, ?, 1, ?)",
            (
                name or url,
                json.dumps({"url": url, "mode": mode, "selector": selector}),
                interval_seconds,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    flash(f"Added page watcher: {name or url}", "info")
    return redirect(url_for("sources.list_sources"))
