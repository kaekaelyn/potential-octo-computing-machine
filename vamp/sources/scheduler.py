"""APScheduler wiring: per-source interval polling with jitter and a
generous misfire grace, so a phone process that slept through several
scheduled polls fires once on wake instead of replaying every missed run
(PLAN.md "Phone realities" §2). Jobs are reconciled against the ``sources``
table every minute so enabling/disabling/adding a source via ``/sources``
takes effect without restarting the process.

Independent from catch-up-on-open (``vamp/sources/catchup.py``): this
module handles "the app is open and running"; catch-up-on-open handles
"the whole process was just killed and restarted" by checking staleness
synchronously on the next page load.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from vamp import db as vamp_db
from vamp.config import Config
from vamp.sources import runner

RECONCILE_INTERVAL_SECONDS = 60
MIN_JITTER_SECONDS = 30
MAX_JITTER_SECONDS = 600


def _jitter_for(interval_seconds: int) -> int:
    return min(MAX_JITTER_SECONDS, max(MIN_JITTER_SECONDS, interval_seconds // 10))


def _job_id(source_id: int) -> str:
    return f"source-{source_id}"


def _run_source_job(db_path: Path, vamp_config: Config, source_id: int) -> None:
    conn = vamp_db.get_connection(db_path)
    try:
        source_row = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
        if source_row is not None:
            runner.run_source(conn, vamp_config, source_row)
    finally:
        conn.close()


def reconcile_jobs(scheduler, conn: sqlite3.Connection, vamp_config: Config, db_path: Path) -> None:
    """Add a job for every enabled source that doesn't have one yet; remove
    jobs belonging to sources that are now disabled or deleted."""
    enabled_ids: set[int] = set()
    for row in conn.execute("SELECT * FROM sources WHERE enabled = 1"):
        enabled_ids.add(row["id"])
        job_id = _job_id(row["id"])
        if scheduler.get_job(job_id) is not None:
            continue
        interval_seconds = row["interval_seconds"]
        scheduler.add_job(
            _run_source_job,
            trigger=IntervalTrigger(seconds=interval_seconds, jitter=_jitter_for(interval_seconds)),
            id=job_id,
            args=[db_path, vamp_config, row["id"]],
            replace_existing=True,
            coalesce=True,
            misfire_grace_time=interval_seconds,
            max_instances=1,
        )

    for job in scheduler.get_jobs():
        if not job.id.startswith("source-"):
            continue
        source_id = int(job.id.removeprefix("source-"))
        if source_id not in enabled_ids:
            scheduler.remove_job(job.id)


_scheduler_lock = threading.Lock()
_started_scheduler: BackgroundScheduler | None = None


def start_scheduler(vamp_config: Config) -> BackgroundScheduler:
    """Start the process-wide background scheduler. Idempotent: calling it
    again returns the already-running instance instead of starting a
    second one (guards against double-start from re-imports/reloaders)."""
    global _started_scheduler
    with _scheduler_lock:
        if _started_scheduler is not None:
            return _started_scheduler

        scheduler = BackgroundScheduler()

        def _reconcile() -> None:
            conn = vamp_db.get_connection(vamp_config.db_path)
            try:
                reconcile_jobs(scheduler, conn, vamp_config, vamp_config.db_path)
            finally:
                conn.close()

        _reconcile()  # jobs exist immediately, not after the first 60s tick
        scheduler.add_job(
            _reconcile,
            trigger=IntervalTrigger(seconds=RECONCILE_INTERVAL_SECONDS),
            id="reconcile-sources",
            replace_existing=True,
        )
        scheduler.start()
        _started_scheduler = scheduler
        return scheduler
