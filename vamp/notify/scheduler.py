"""Wires the morning digest and Sunday Outreach Sprint notification jobs
onto the process-wide APScheduler instance (PLAN.md §7/§9/§12 M7), reusing
the same ``BackgroundScheduler`` the M2 source-polling and M5 nightly-AI
jobs run on (``vamp.sources.scheduler.start_scheduler``) rather than
starting another scheduler thread.

A generous misfire grace means a phone that was asleep through the
scheduled hour still fires once on wake instead of never firing — the same
shape as ``vamp.ai.scheduler``. Notifications deliberately do *not* also
run via catch-up-on-open: that would mean re-opening the app minutes after
a missed digest fires a second, redundant one; ``vamp.notify.jobs``'s
once-per-day/week guard exists precisely so the scheduled path alone is
enough.
"""

from __future__ import annotations

from apscheduler.triggers.cron import CronTrigger

from vamp import db as vamp_db
from vamp.config import Config
from vamp.notify.jobs import send_morning_digest, send_sunday_sprint

DIGEST_JOB_ID = "notify-morning-digest"
SPRINT_JOB_ID = "notify-sunday-sprint"

# PLAN.md §7: "Daily digest (termux-notification, morning)" /
# "Weekly Outreach Sprint (Sunday evening)".
DIGEST_HOUR = 8
SPRINT_DAY_OF_WEEK = "sun"
SPRINT_HOUR = 18

MISFIRE_GRACE_SECONDS = 6 * 3600


def _run_digest_job(db_path, vamp_config: Config) -> None:
    conn = vamp_db.get_connection(db_path)
    try:
        send_morning_digest(conn, vamp_config)
    finally:
        conn.close()


def _run_sprint_job(db_path, vamp_config: Config) -> None:
    conn = vamp_db.get_connection(db_path)
    try:
        send_sunday_sprint(conn, vamp_config)
    finally:
        conn.close()


def add_notification_jobs(scheduler, vamp_config: Config) -> None:
    if scheduler.get_job(DIGEST_JOB_ID) is None:
        scheduler.add_job(
            _run_digest_job,
            trigger=CronTrigger(hour=DIGEST_HOUR, minute=0),
            id=DIGEST_JOB_ID,
            args=[vamp_config.db_path, vamp_config],
            replace_existing=True,
            coalesce=True,
            misfire_grace_time=MISFIRE_GRACE_SECONDS,
            max_instances=1,
        )
    if scheduler.get_job(SPRINT_JOB_ID) is None:
        scheduler.add_job(
            _run_sprint_job,
            trigger=CronTrigger(day_of_week=SPRINT_DAY_OF_WEEK, hour=SPRINT_HOUR, minute=0),
            id=SPRINT_JOB_ID,
            args=[vamp_config.db_path, vamp_config],
            replace_existing=True,
            coalesce=True,
            misfire_grace_time=MISFIRE_GRACE_SECONDS,
            max_instances=1,
        )
