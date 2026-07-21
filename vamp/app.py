"""Flask app factory."""

from __future__ import annotations

import secrets

from flask import Flask, render_template, send_from_directory

from . import db as vamp_db
from .config import Config, load_config


def create_app(config: Config | None = None) -> Flask:
    config = config or load_config()
    app = Flask(__name__)
    app.config["VAMP_CONFIG"] = config
    # Local-only app (binds 127.0.0.1) — a session-lifetime secret is enough
    # for flash messages; nothing here is a durable auth credential.
    app.config["SECRET_KEY"] = secrets.token_hex(32)

    from .capture.routes import bp as capture_bp
    from .leads.routes import bp as leads_bp
    from .patrol.routes import bp as patrol_bp

    app.register_blueprint(capture_bp)
    app.register_blueprint(leads_bp)
    app.register_blueprint(patrol_bp)

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

    @app.route("/manifest.webmanifest")
    def manifest():
        response = send_from_directory(app.static_folder, "manifest.webmanifest")
        response.headers["Content-Type"] = "application/manifest+json"
        return response

    @app.route("/service-worker.js")
    def service_worker():
        response = send_from_directory(app.static_folder, "service-worker.js")
        response.headers["Content-Type"] = "application/javascript"
        # Root-scoped even though the file is served from /static/.
        response.headers["Service-Worker-Allowed"] = "/"
        return response

    return app
