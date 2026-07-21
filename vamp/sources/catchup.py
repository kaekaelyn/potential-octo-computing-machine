"""Catch-up-on-open: every UI page load checks source staleness and
triggers an immediate poll of anything overdue (PLAN.md "Phone realities":
even if Android killed the process overnight, opening the app self-heals
within seconds). Runs in a background thread so it never blocks the page
load; a lock skips a second trigger while a run is already in flight.
"""

from __future__ import annotations

import threading

from vamp import db as vamp_db
from vamp.config import Config
from vamp.sources import runner

_catchup_lock = threading.Lock()


def trigger_catch_up_if_overdue(
    vamp_config: Config, *, background: bool = True
) -> threading.Thread | None:
    conn = vamp_db.get_connection(vamp_config.db_path)
    try:
        due = runner.find_due_sources(conn)
    finally:
        conn.close()
    if not due:
        return None
    if not _catchup_lock.acquire(blocking=False):
        return None  # a catch-up run is already in flight

    def _run() -> None:
        try:
            run_conn = vamp_db.get_connection(vamp_config.db_path)
            try:
                runner.run_due_sources(run_conn, vamp_config)
            finally:
                run_conn.close()
        finally:
            _catchup_lock.release()

    if background:
        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        return thread
    _run()
    return None


def install_catchup_middleware(app, vamp_config: Config, *, sync: bool = False) -> None:
    @app.before_request
    def _catch_up_on_open():
        trigger_catch_up_if_overdue(vamp_config, background=not sync)
