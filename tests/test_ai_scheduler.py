from __future__ import annotations

from pathlib import Path

from vamp.ai import scheduler as ai_scheduler
from vamp.config import load_config


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


def test_add_nightly_job_registers_once(vamp_home: Path):
    config = load_config(home=vamp_home)
    fake = _FakeScheduler()

    ai_scheduler.add_nightly_job(fake, config)

    assert ai_scheduler.JOB_ID in fake.jobs
    job = fake.jobs[ai_scheduler.JOB_ID]
    assert job["misfire_grace_time"] == ai_scheduler.MISFIRE_GRACE_SECONDS
    assert job["coalesce"] is True
    assert job["max_instances"] == 1


def test_add_nightly_job_is_idempotent(vamp_home: Path):
    config = load_config(home=vamp_home)
    fake = _FakeScheduler()

    ai_scheduler.add_nightly_job(fake, config)
    ai_scheduler.add_nightly_job(fake, config)

    assert len(fake.jobs) == 1
