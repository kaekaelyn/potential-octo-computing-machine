from __future__ import annotations

from pathlib import Path

from vamp import db as vamp_db
from vamp.ai import notes as notes_service
from vamp.ai.provider import NoneProvider, ProviderError
from vamp.config import load_config
from vamp.prospects.pipeline import create_prospect


def _conn(vamp_home: Path):
    config = load_config(home=vamp_home)
    return vamp_db.get_connection(config.db_path)


class _RaisingProvider:
    name = "claude"

    def complete(self, system, prompt, schema):
        raise ProviderError("boom")


def _prospect(conn):
    prospect_id = create_prospect(
        conn, {"name": "First Baptist", "category": "church", "angle": "sub list"}
    )
    return conn.execute("SELECT * FROM prospects WHERE id = ?", (prospect_id,)).fetchone()


def test_draft_followup_caches_and_falls_back(vamp_home: Path):
    conn = _conn(vamp_home)
    prospect = _prospect(conn)

    result = notes_service.draft_followup(conn, _RaisingProvider(), prospect)

    assert result["provider"] == "none"
    cached = notes_service.latest_followup(conn, prospect["id"])
    assert cached is not None


def test_draft_sub_availability_with_prospect(vamp_home: Path):
    conn = _conn(vamp_home)
    prospect = _prospect(conn)

    result = notes_service.draft_sub_availability(conn, NoneProvider(), prospect, "March 9")

    assert result["date"] == "March 9"
    assert result["body"]


def test_draft_sub_availability_without_prospect(vamp_home: Path):
    conn = _conn(vamp_home)

    result = notes_service.draft_sub_availability(conn, NoneProvider(), None, "this Sunday")

    assert result["date"] == "this Sunday"
    from vamp.ai import drafts as drafts_service

    cached = drafts_service.latest_draft(
        conn, kind=notes_service.SUB_AVAILABILITY_KIND, ref_kind=None, ref_id=None
    )
    assert cached is not None
