from __future__ import annotations

from pathlib import Path

from vamp import db as vamp_db
from vamp.sources import scheduler


class _FakeJob:
    def __init__(self, job_id: str):
        self.id = job_id


class _FakeScheduler:
    """Records add_job/remove_job calls without touching real threads."""

    def __init__(self):
        self.jobs: dict[str, dict] = {}

    def get_job(self, job_id: str):
        return _FakeJob(job_id) if job_id in self.jobs else None

    def get_jobs(self):
        return [_FakeJob(job_id) for job_id in self.jobs]

    def add_job(self, func, trigger, id, args=None, **kwargs):
        self.jobs[id] = {"func": func, "trigger": trigger, "args": args, **kwargs}

    def remove_job(self, job_id: str):
        del self.jobs[job_id]


def _insert_source(conn, *, enabled=1, interval_seconds=3600, name="Test"):
    cur = conn.execute(
        "INSERT INTO sources (kind, name, config_json, enabled, interval_seconds) "
        "VALUES ('rss', ?, '{}', ?, ?)",
        (name, enabled, interval_seconds),
    )
    conn.commit()
    return cur.lastrowid


def test_reconcile_adds_a_job_per_enabled_source(tmp_path: Path):
    db_path = tmp_path / "vamp.db"
    conn = vamp_db.get_connection(db_path)
    source_id = _insert_source(conn)
    fake = _FakeScheduler()

    scheduler.reconcile_jobs(fake, conn, vamp_config=None, db_path=db_path)

    assert f"source-{source_id}" in fake.jobs
    job = fake.jobs[f"source-{source_id}"]
    assert job["misfire_grace_time"] == 3600
    assert job["coalesce"] is True
    conn.close()


def test_reconcile_skips_disabled_sources(tmp_path: Path):
    db_path = tmp_path / "vamp.db"
    conn = vamp_db.get_connection(db_path)
    _insert_source(conn, enabled=0)
    fake = _FakeScheduler()

    scheduler.reconcile_jobs(fake, conn, vamp_config=None, db_path=db_path)

    assert fake.jobs == {}
    conn.close()


def test_reconcile_removes_job_for_now_disabled_source(tmp_path: Path):
    db_path = tmp_path / "vamp.db"
    conn = vamp_db.get_connection(db_path)
    source_id = _insert_source(conn, enabled=1)
    fake = _FakeScheduler()
    scheduler.reconcile_jobs(fake, conn, vamp_config=None, db_path=db_path)
    assert f"source-{source_id}" in fake.jobs

    conn.execute("UPDATE sources SET enabled = 0 WHERE id = ?", (source_id,))
    conn.commit()
    scheduler.reconcile_jobs(fake, conn, vamp_config=None, db_path=db_path)

    assert f"source-{source_id}" not in fake.jobs
    conn.close()


def test_reconcile_does_not_duplicate_existing_job(tmp_path: Path):
    db_path = tmp_path / "vamp.db"
    conn = vamp_db.get_connection(db_path)
    source_id = _insert_source(conn)
    fake = _FakeScheduler()

    scheduler.reconcile_jobs(fake, conn, vamp_config=None, db_path=db_path)
    scheduler.reconcile_jobs(fake, conn, vamp_config=None, db_path=db_path)

    assert len(fake.jobs) == 1
    assert f"source-{source_id}" in fake.jobs
    conn.close()


def test_jitter_is_bounded():
    assert scheduler._jitter_for(60) == scheduler.MIN_JITTER_SECONDS
    assert scheduler._jitter_for(3600) == 360
    assert scheduler._jitter_for(10_000_000) == scheduler.MAX_JITTER_SECONDS
