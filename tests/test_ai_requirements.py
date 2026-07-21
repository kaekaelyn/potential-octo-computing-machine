from __future__ import annotations

from pathlib import Path

from vamp import db as vamp_db
from vamp.ai import requirements_ai
from vamp.ai.provider import NoneProvider, ProviderError
from vamp.config import load_config


def _conn(vamp_home: Path):
    config = load_config(home=vamp_home)
    return vamp_db.get_connection(config.db_path)


def _insert_lead(conn, *, title="Pianist wanted", description="Solo piano for cocktail hour."):
    cur = conn.execute(
        "INSERT INTO leads (source_id, kind, dedupe_hash, url_hash, title, description, state) "
        "VALUES (NULL, 'gig', ?, ?, ?, ?, 'inbox')",
        (title, title, title, description),
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


def test_extract_and_merge_adds_new_kinds(vamp_home: Path):
    conn = _conn(vamp_home)
    lead_id = _insert_lead(conn)
    lead = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()

    result = requirements_ai.extract_and_merge(
        conn,
        _FixedProvider({"requirements": [{"kind": "headshot", "detail": "send a current photo"}]}),
        lead,
    )

    assert result["added"] == 1
    row = conn.execute(
        "SELECT * FROM requirements WHERE lead_id = ? AND kind = 'headshot'", (lead_id,)
    ).fetchone()
    assert row is not None
    assert row["detail"] == "send a current photo"


def test_extract_and_merge_never_duplicates_existing_kind(vamp_home: Path):
    conn = _conn(vamp_home)
    lead_id = _insert_lead(conn, description="Please send a bio and headshot.")
    lead = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    # Heuristic pass (M3) already ran via leads.service on insert in real
    # usage; simulate it directly here since this test inserts leads raw.
    from vamp.vault.matching import sync_requirements

    sync_requirements(conn, lead_id, f"{lead['title']}\n{lead['description']}")
    existing_count = conn.execute(
        "SELECT COUNT(*) AS n FROM requirements WHERE lead_id = ?", (lead_id,)
    ).fetchone()["n"]
    assert existing_count >= 1

    result = requirements_ai.extract_and_merge(
        conn,
        _FixedProvider({"requirements": [{"kind": "headshot", "detail": "a duplicate find"}]}),
        lead,
    )

    assert result["added"] == 0
    rows = conn.execute(
        "SELECT * FROM requirements WHERE lead_id = ? AND kind = 'headshot'", (lead_id,)
    ).fetchall()
    assert len(rows) == 1


def test_extract_and_merge_ignores_unknown_kinds(vamp_home: Path):
    conn = _conn(vamp_home)
    lead_id = _insert_lead(conn)
    lead = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()

    result = requirements_ai.extract_and_merge(
        conn,
        _FixedProvider({"requirements": [{"kind": "not-a-real-kind", "detail": "x"}]}),
        lead,
    )

    assert result["added"] == 0
    assert requirements_ai._normalize({"requirements": [{"kind": "not-a-real-kind"}]}) == []


def test_extract_and_merge_is_cached_by_text_hash(vamp_home: Path):
    conn = _conn(vamp_home)
    lead_id = _insert_lead(conn)
    lead = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()

    requirements_ai.extract_and_merge(
        conn, _FixedProvider({"requirements": [{"kind": "headshot", "detail": "first pass"}]}), lead
    )
    # Same text -> cache hit, so a raising provider must not blow up.
    lead_again = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    result = requirements_ai.extract_and_merge(conn, _RaisingProvider(), lead_again)
    assert result["provider"] == "claude"  # served from the original cached (claude) draft


def test_extract_and_merge_recomputes_after_text_changes(vamp_home: Path):
    conn = _conn(vamp_home)
    lead_id = _insert_lead(conn, description="Original text.")
    lead = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    requirements_ai.extract_and_merge(
        conn, _FixedProvider({"requirements": [{"kind": "headshot", "detail": "x"}]}), lead
    )

    conn.execute("UPDATE leads SET description = ? WHERE id = ?", ("Edited text.", lead_id))
    conn.commit()
    lead_edited = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()

    result = requirements_ai.extract_and_merge(
        conn,
        _FixedProvider({"requirements": [{"kind": "cv", "detail": "send a resume"}]}),
        lead_edited,
    )

    assert result["requirements"] == [{"kind": "cv", "detail": "send a resume"}]


def test_leads_needing_extraction_and_batch(vamp_home: Path):
    conn = _conn(vamp_home)
    _insert_lead(conn, title="Lead A")
    _insert_lead(conn, title="Lead B")

    pending = requirements_ai.leads_needing_extraction(conn)
    assert len(pending) == 2

    results = requirements_ai.extract_for_new_leads(conn, NoneProvider())
    assert len(results) == 2
    assert requirements_ai.leads_needing_extraction(conn) == []
