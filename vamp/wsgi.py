"""Entry point: serve Vamp behind waitress, per PLAN.md's WSGI-server choice."""

from __future__ import annotations

from waitress import serve

from .ai.scheduler import add_nightly_job
from .app import create_app
from .config import load_config
from .notify.scheduler import add_notification_jobs
from .sources.scheduler import start_scheduler


def main() -> None:
    config = load_config()
    app = create_app(config)
    scheduler = start_scheduler(config)
    add_nightly_job(scheduler, config)
    add_notification_jobs(scheduler, config)
    print(f"Vamp serving on http://{config.host}:{config.port}  (db: {config.db_path})")
    serve(app, host=config.host, port=config.port)


if __name__ == "__main__":
    main()
