from __future__ import annotations

import json
from pathlib import Path

from vamp import db as vamp_db
from vamp.ai.batch import run_nightly
from vamp.ai.provider import NoneProvider
from vamp.config import load_config


def _conn_and_config(vamp_home: Path):
    config = load_config(home=vamp_home)
    return vamp_db.get_connection(config.db_path), config


def _insert_lead(conn, *, title="Pianist wanted"):
    conn.execute(
        "INSERT INTO leads (source_id, kind, dedupe_hash, url_hash, title, description, state) "
        "VALUES (NULL, 'gig', ?, ?, ?, 'Solo piano', 'inbox')",
        (title, title, title),
    )
    conn.commit()


def _insert_excluded_degree_lead(conn, *, title="Church pianist"):
    conn.execute(
        "INSERT INTO leads (source_id, kind, dedupe_hash, url_hash, title, description, "
        "state, excluded_reason) "
        "VALUES (NULL, 'job', ?, ?, ?, 'Bachelor degree in Music required.', "
        "'excluded', 'degree-wall')",
        (title, title, title),
    )
    conn.commit()


def test_run_nightly_scores_and_reviews_and_extracts(vamp_home: Path):
    conn, config = _conn_and_config(vamp_home)
    _insert_lead(conn, title="Lead A")
    _insert_excluded_degree_lead(conn)

    summary = run_nightly(conn, config, provider=NoneProvider())

    assert summary["scored"] == 1
    assert summary["degree_reviewed"] == 1
    assert summary["degree_overridden"] == 0
    # Excluded leads are skipped, same as scoring — only the non-excluded
    # lead is in the extraction queue.
    assert summary["requirements_extracted"] == 1
    assert summary["providers_used"] == ["none"]

    event = conn.execute(
        "SELECT * FROM events WHERE kind = 'ai_nightly_run' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert event is not None
    payload = json.loads(event["payload_json"])
    assert payload["scored"] == 1


def test_run_nightly_is_idempotent_second_run_does_nothing_new(vamp_home: Path):
    conn, config = _conn_and_config(vamp_home)
    _insert_lead(conn)

    run_nightly(conn, config, provider=NoneProvider())
    summary = run_nightly(conn, config, provider=NoneProvider())

    assert summary["scored"] == 0
    assert summary["requirements_extracted"] == 0


def test_run_nightly_never_raises_when_provider_is_broken(vamp_home: Path):
    from vamp.ai.provider import ProviderError

    class _BrokenProvider:
        name = "claude"

        def complete(self, system, prompt, schema):
            raise ProviderError("simulated: CLI killed mid-run")

    conn, config = _conn_and_config(vamp_home)
    _insert_lead(conn)
    _insert_excluded_degree_lead(conn)

    summary = run_nightly(conn, config, provider=_BrokenProvider())

    assert summary["scored"] == 1
    assert summary["providers_used"] == ["none"]
