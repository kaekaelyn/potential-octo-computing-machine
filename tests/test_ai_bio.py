from __future__ import annotations

from pathlib import Path

from vamp import db as vamp_db
from vamp.ai import bio as bio_service
from vamp.ai.provider import NoneProvider, ProviderError
from vamp.config import load_config
from vamp.profile import service as profile_service


def _conn(vamp_home: Path):
    config = load_config(home=vamp_home)
    return vamp_db.get_connection(config.db_path)


class _RaisingProvider:
    name = "claude"

    def complete(self, system, prompt, schema):
        raise ProviderError("boom")


def test_draft_bio_uses_profile_defaults(vamp_home: Path):
    conn = _conn(vamp_home)

    result = bio_service.draft_bio(conn, NoneProvider())

    assert "Kaelyn" in result["bio_50"]
    assert result["provider"] == "none"


def test_draft_bio_reflects_saved_profile(vamp_home: Path):
    conn = _conn(vamp_home)
    profile_service.set_profile(
        conn, {"display_name": "K. Lyn", "instrument": "keyboardist", "home_area": "Norman, OK"}
    )

    system, prompt, schema = bio_service.build_prompt(conn)

    assert "K. Lyn" in prompt
    assert schema["context"]["home_area"] == "Norman, OK"


def test_draft_bio_caches_and_latest_returns_most_recent(vamp_home: Path):
    conn = _conn(vamp_home)

    bio_service.draft_bio(conn, NoneProvider())
    row = bio_service.latest_bio(conn)

    assert row is not None
    assert row["ref_kind"] == "profile"
    assert row["ref_id"] is None


def test_draft_bio_falls_back_on_provider_failure(vamp_home: Path):
    conn = _conn(vamp_home)

    result = bio_service.draft_bio(conn, _RaisingProvider())

    assert result["provider"] == "none"
    assert result["bio_50"]
