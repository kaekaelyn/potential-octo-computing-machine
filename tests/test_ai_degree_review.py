from __future__ import annotations

from pathlib import Path

from vamp import db as vamp_db
from vamp.ai import degree_review
from vamp.ai.provider import ProviderError
from vamp.config import load_config


def _conn(vamp_home: Path):
    config = load_config(home=vamp_home)
    return vamp_db.get_connection(config.db_path)


def _insert_excluded_lead(conn, *, reasons: str, title="Church pianist"):
    cur = conn.execute(
        "INSERT INTO leads (source_id, kind, dedupe_hash, url_hash, title, description, "
        "state, excluded_reason) "
        "VALUES (NULL, 'job', ?, ?, ?, 'Bachelor degree in Music required.', 'excluded', ?)",
        (title, title, title, reasons),
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
        raise ProviderError("boom")


def test_review_lead_overrides_and_restores_when_no_other_reason(vamp_home: Path):
    conn = _conn(vamp_home)
    lead_id = _insert_excluded_lead(conn, reasons="degree-wall")
    lead = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()

    result = degree_review.review_lead(
        conn, _FixedProvider({"override": True, "reasoning": "says preferred, not required"}), lead
    )

    assert result["override"] is True
    updated = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    assert updated["state"] == "inbox"
    assert updated["excluded_reason"] is None


def test_review_lead_overrides_but_keeps_other_exclusion_reasons(vamp_home: Path):
    conn = _conn(vamp_home)
    lead_id = _insert_excluded_lead(conn, reasons="degree-wall,teaching")
    lead = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()

    degree_review.review_lead(
        conn, _FixedProvider({"override": True, "reasoning": "not a hard requirement"}), lead
    )

    updated = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    assert updated["state"] == "excluded"
    assert updated["excluded_reason"] == "teaching"


def test_review_lead_standing_pat_leaves_lead_excluded(vamp_home: Path):
    conn = _conn(vamp_home)
    lead_id = _insert_excluded_lead(conn, reasons="degree-wall")
    lead = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()

    result = degree_review.review_lead(
        conn, _FixedProvider({"override": False, "reasoning": "genuinely required"}), lead
    )

    assert result["override"] is False
    updated = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    assert updated["state"] == "excluded"
    assert updated["excluded_reason"] == "degree-wall"


def test_review_lead_is_cached_and_not_recomputed(vamp_home: Path):
    conn = _conn(vamp_home)
    lead_id = _insert_excluded_lead(conn, reasons="degree-wall")
    lead = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()

    degree_review.review_lead(
        conn, _FixedProvider({"override": True, "reasoning": "first pass"}), lead
    )
    # A second call with a provider that would raise should hit the cache
    # instead, proving it isn't re-billed to the subscription.
    lead_after = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    result = degree_review.review_lead(conn, _RaisingProvider(), lead_after)
    assert result["reasoning"] == "first pass"


def test_falls_back_to_heuristic_on_provider_failure_standing_pat(vamp_home: Path):
    conn = _conn(vamp_home)
    lead_id = _insert_excluded_lead(conn, reasons="degree-wall")
    lead = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()

    result = degree_review.review_lead(conn, _RaisingProvider(), lead)

    assert result["provider"] == "none"
    assert result["override"] is False
    updated = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    assert updated["state"] == "excluded"


def test_pending_degree_reviews_only_returns_unreviewed(vamp_home: Path):
    conn = _conn(vamp_home)
    reviewed_id = _insert_excluded_lead(conn, reasons="degree-wall", title="Reviewed")
    pending_id = _insert_excluded_lead(conn, reasons="degree-wall", title="Pending")
    other_reason_id = _insert_excluded_lead(conn, reasons="teaching", title="Not degree wall")

    lead = conn.execute("SELECT * FROM leads WHERE id = ?", (reviewed_id,)).fetchone()
    degree_review.review_lead(conn, _FixedProvider({"override": False, "reasoning": "x"}), lead)

    pending = {row["id"] for row in degree_review.pending_degree_reviews(conn)}
    assert pending == {pending_id}
    assert other_reason_id not in pending
    assert reviewed_id not in pending


def test_review_pending_degree_exclusions_batches(vamp_home: Path):
    conn = _conn(vamp_home)
    _insert_excluded_lead(conn, reasons="degree-wall", title="A")
    _insert_excluded_lead(conn, reasons="degree-wall", title="B")

    from vamp.ai.provider import NoneProvider

    results = degree_review.review_pending_degree_exclusions(conn, NoneProvider())
    assert len(results) == 2
    assert degree_review.pending_degree_reviews(conn) == []
