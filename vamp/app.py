"""Flask app factory."""

from __future__ import annotations

import secrets

from flask import Flask, render_template, send_from_directory

from . import db as vamp_db
from .config import Config, load_config
from .seeds.loader import ensure_seed_data
from .sources.catchup import install_catchup_middleware
from .sources.runner import ensure_default_sources
from .vault.kit import ensure_default_kit_tasks


def create_app(config: Config | None = None, *, catchup_sync: bool = False) -> Flask:
    config = config or load_config()
    app = Flask(__name__)
    app.config["VAMP_CONFIG"] = config
    # Local-only app (binds 127.0.0.1) — a session-lifetime secret is enough
    # for flash messages; nothing here is a durable auth credential.
    app.config["SECRET_KEY"] = secrets.token_hex(32)

    conn = vamp_db.get_connection(config.db_path)
    try:
        ensure_default_sources(conn)
        ensure_default_kit_tasks(conn)
        ensure_seed_data(conn)
    finally:
        conn.close()

    from .ai.routes import bp as ai_bp
    from .capture.routes import bp as capture_bp
    from .gigs.routes import bp as gigs_bp
    from .kit.routes import bp as kit_bp
    from .leads.routes import bp as leads_bp
    from .metrics.routes import bp as metrics_bp
    from .notify.routes import bp as notify_bp
    from .patrol.routes import bp as patrol_bp
    from .people.routes import bp as people_bp
    from .playbooks.routes import bp as playbooks_bp
    from .profile.routes import bp as profile_bp
    from .prospects.routes import bp as prospects_bp
    from .reminders.routes import bp as reminders_bp
    from .scene.routes import bp as scene_bp
    from .sources.routes import bp as sources_bp
    from .vault.routes import bp as vault_bp

    app.register_blueprint(ai_bp)
    app.register_blueprint(capture_bp)
    app.register_blueprint(gigs_bp)
    app.register_blueprint(kit_bp)
    app.register_blueprint(leads_bp)
    app.register_blueprint(metrics_bp)
    app.register_blueprint(notify_bp)
    app.register_blueprint(patrol_bp)
    app.register_blueprint(people_bp)
    app.register_blueprint(playbooks_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(prospects_bp)
    app.register_blueprint(reminders_bp)
    app.register_blueprint(scene_bp)
    app.register_blueprint(sources_bp)
    app.register_blueprint(vault_bp)

    install_catchup_middleware(app, config, sync=catchup_sync)

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
