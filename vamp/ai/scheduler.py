"""Wires the nightly AI batch job onto the process-wide APScheduler
instance (PLAN.md §9: "queued and batched...nightly scoring run"). Reuses
the same ``BackgroundScheduler`` the M2 source-polling jobs run on
(``vamp.sources.scheduler.start_scheduler``) rather than starting a second
scheduler thread.

A generous misfire grace means a phone that was asleep through 3am still
runs the batch once when it wakes, instead of never running it at all —
unlike source polling, it deliberately does *not* also run via
catch-up-on-open, since that would defeat the point of batching against
subscription/battery limits.
"""

from __future__ import annotations

from apscheduler.triggers.cron import CronTrigger

from vamp import db as vamp_db
from vamp.ai.batch import run_nightly
from vamp.config import Config

JOB_ID = "ai-nightly"
NIGHTLY_HOUR = 3  # local-time-agnostic: the phone's own clock, per PLAN.md's "nightly"
MISFIRE_GRACE_SECONDS = 6 * 3600


def _run_nightly_job(db_path, vamp_config: Config) -> None:
    conn = vamp_db.get_connection(db_path)
    try:
        run_nightly(conn, vamp_config)
    finally:
        conn.close()


def add_nightly_job(scheduler, vamp_config: Config) -> None:
    if scheduler.get_job(JOB_ID) is not None:
        return
    scheduler.add_job(
        _run_nightly_job,
        trigger=CronTrigger(hour=NIGHTLY_HOUR, minute=0),
        id=JOB_ID,
        args=[vamp_config.db_path, vamp_config],
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=MISFIRE_GRACE_SECONDS,
        max_instances=1,
    )
