from __future__ import annotations

from pathlib import Path

from vamp import db as vamp_db
from vamp.ai import scoring
from vamp.ai.provider import NoneProvider, ProviderError
from vamp.config import load_config


def _conn(vamp_home: Path):
    config = load_config(home=vamp_home)
    return vamp_db.get_connection(config.db_path)


def _insert_lead(conn, *, state="inbox", pay_kind="flat", pay_min=200, title="Pianist wanted"):
    cur = conn.execute(
        "INSERT INTO leads (source_id, kind, dedupe_hash, url_hash, title, org, location, "
        "pay_min, pay_max, pay_kind, description, state) "
        "VALUES (NULL, 'gig', ?, ?, ?, 'Org', 'Edmond, OK', ?, ?, ?, 'Solo piano', ?)",
        (title, title, title, pay_min, pay_min, pay_kind, state),
    )
    conn.commit()
    return cur.lastrowid


class _FixedProvider:
    name = "claude"

    def __init__(self, result):
        self.result = result

    def complete(self, system, prompt, schema):
        return self.result


class _RaisingProvider:
    name = "claude"

    def complete(self, system, prompt, schema):
        raise ProviderError("simulated failure")


def test_score_lead_caches_in_scores_table(vamp_home: Path):
    conn = _conn(vamp_home)
    lead_id = _insert_lead(conn)
    lead = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()

    result = scoring.score_lead(
        conn, _FixedProvider({"score": 77, "rationale": "great", "flags": []}), lead
    )

    assert result["score"] == 77
    assert result["provider"] == "claude"
    row = conn.execute("SELECT * FROM scores WHERE lead_id = ?", (lead_id,)).fetchone()
    assert row["scorer"] == "claude"
    assert row["score"] == 77


def test_score_lead_upserts_not_duplicates(vamp_home: Path):
    conn = _conn(vamp_home)
    lead_id = _insert_lead(conn)
    lead = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()

    scoring.score_lead(conn, _FixedProvider({"score": 50, "rationale": "a", "flags": []}), lead)
    scoring.score_lead(conn, _FixedProvider({"score": 90, "rationale": "b", "flags": []}), lead)

    rows = conn.execute("SELECT * FROM scores WHERE lead_id = ?", (lead_id,)).fetchall()
    assert len(rows) == 1
    assert rows[0]["score"] == 90


def test_score_lead_falls_back_to_none_and_still_caches(vamp_home: Path):
    conn = _conn(vamp_home)
    lead_id = _insert_lead(conn)
    lead = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()

    result = scoring.score_lead(conn, _RaisingProvider(), lead)

    assert result["provider"] == "none"
    row = conn.execute("SELECT * FROM scores WHERE lead_id = ?", (lead_id,)).fetchone()
    assert row["scorer"] == "none"


def test_score_clamps_out_of_range_scores(vamp_home: Path):
    conn = _conn(vamp_home)
    lead_id = _insert_lead(conn)
    lead = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()

    result = scoring.score_lead(
        conn, _FixedProvider({"score": 500, "rationale": "", "flags": []}), lead
    )
    assert result["score"] == 100

    result = scoring.score_lead(
        conn, _FixedProvider({"score": -20, "rationale": "", "flags": []}), lead
    )
    assert result["score"] == 0


def test_unscored_leads_excludes_excluded_and_already_scored(vamp_home: Path):
    conn = _conn(vamp_home)
    new_id = _insert_lead(conn, title="New lead")
    excluded_id = _insert_lead(conn, title="Excluded lead", state="excluded")
    scored_id = _insert_lead(conn, title="Already scored")
    lead = conn.execute("SELECT * FROM leads WHERE id = ?", (scored_id,)).fetchone()
    scoring.score_lead(conn, _FixedProvider({"score": 1, "rationale": "", "flags": []}), lead)

    unscored = scoring.unscored_leads(conn)
    ids = {row["id"] for row in unscored}

    assert new_id in ids
    assert excluded_id not in ids
    assert scored_id not in ids


def test_score_new_leads_batches_all_unscored(vamp_home: Path):
    conn = _conn(vamp_home)
    _insert_lead(conn, title="Lead A")
    _insert_lead(conn, title="Lead B")

    results = scoring.score_new_leads(conn, NoneProvider())

    assert len(results) == 2
    assert conn.execute("SELECT COUNT(*) AS n FROM scores").fetchone()["n"] == 2


def test_score_new_leads_is_idempotent_across_runs(vamp_home: Path):
    conn = _conn(vamp_home)
    _insert_lead(conn, title="Lead A")

    scoring.score_new_leads(conn, NoneProvider())
    second_run = scoring.score_new_leads(conn, NoneProvider())

    assert second_run == []  # nothing left unscored, so nothing scored twice
