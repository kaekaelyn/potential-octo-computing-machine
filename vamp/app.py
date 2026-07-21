"""Flask app factory — M0 ships a placeholder dashboard only."""

from __future__ import annotations

from flask import Flask, render_template

from . import db as vamp_db
from .config import Config, load_config


def create_app(config: Config | None = None) -> Flask:
    config = config or load_config()
    app = Flask(__name__)
    app.config["VAMP_CONFIG"] = config

    @app.route("/")
    def dashboard():
        conn = vamp_db.get_connection(config.db_path)
        try:
            counts = {
                table: conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
                for table in ("sources", "leads", "prospects", "gigs")
            }
        finally:
            conn.close()
        return render_template(
            "dashboard.html",
            counts=counts,
            db_path=str(config.db_path),
            version=__import__("vamp").__version__,
        )

    @app.route("/healthz")
    def healthz():
        return {"status": "ok"}

    return app
