from __future__ import annotations

from pathlib import Path

from vamp.config import load_config
from vamp.notify import scheduler as notify_scheduler


class _FakeJob:
    def __init__(self, job_id: str):
        self.id = job_id


class _FakeScheduler:
    def __init__(self):
        self.jobs: dict[str, dict] = {}

    def get_job(self, job_id: str):
        return _FakeJob(job_id) if job_id in self.jobs else None

    def add_job(self, func, trigger, id, args=None, **kwargs):
        self.jobs[id] = {"func": func, "trigger": trigger, "args": args, **kwargs}


def test_add_notification_jobs_registers_both(vamp_home: Path):
    config = load_config(home=vamp_home)
    fake = _FakeScheduler()

    notify_scheduler.add_notification_jobs(fake, config)

    assert notify_scheduler.DIGEST_JOB_ID in fake.jobs
    assert notify_scheduler.SPRINT_JOB_ID in fake.jobs

    digest_job = fake.jobs[notify_scheduler.DIGEST_JOB_ID]
    assert digest_job["misfire_grace_time"] == notify_scheduler.MISFIRE_GRACE_SECONDS
    assert digest_job["coalesce"] is True
    assert digest_job["max_instances"] == 1

    sprint_job = fake.jobs[notify_scheduler.SPRINT_JOB_ID]
    assert sprint_job["misfire_grace_time"] == notify_scheduler.MISFIRE_GRACE_SECONDS


def test_add_notification_jobs_is_idempotent(vamp_home: Path):
    config = load_config(home=vamp_home)
    fake = _FakeScheduler()

    notify_scheduler.add_notification_jobs(fake, config)
    notify_scheduler.add_notification_jobs(fake, config)

    assert len(fake.jobs) == 2
