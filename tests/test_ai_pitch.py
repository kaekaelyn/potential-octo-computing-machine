from __future__ import annotations

from pathlib import Path

from vamp import db as vamp_db
from vamp.ai import pitch as pitch_service
from vamp.ai.provider import NoneProvider, ProviderError
from vamp.config import load_config
from vamp.profile import service as profile_service
from vamp.prospects.pipeline import create_prospect
from vamp.vault.assets import create_asset


def _conn(vamp_home: Path):
    config = load_config(home=vamp_home)
    return vamp_db.get_connection(config.db_path), config


class _RaisingProvider:
    name = "claude"

    def complete(self, system, prompt, schema):
        raise ProviderError("boom")


class _FixedProvider:
    name = "claude"

    def __init__(self, result):
        self.result = result

    def complete(self, system, prompt, schema):
        return self.result


def _prospect(conn):
    prospect_id = create_prospect(
        conn,
        {
            "name": "The Grand Hotel",
            "category": "hotel",
            "angle": "has a lobby grand nobody plays",
        },
    )
    return conn.execute("SELECT * FROM prospects WHERE id = ?", (prospect_id,)).fetchone()


def test_draft_pitch_includes_angle_and_caches(vamp_home: Path):
    conn, _config = _conn(vamp_home)
    prospect = _prospect(conn)

    result = pitch_service.draft_pitch(conn, NoneProvider(), prospect)

    assert "Grand Hotel" in result["subject"] or "Grand Hotel" in result["body"]
    cached = pitch_service.latest_pitch(conn, prospect["id"])
    assert cached is not None
    assert cached["provider"] == "none"


def test_draft_pitch_uses_profile_voice_sample_in_prompt(vamp_home: Path):
    conn, _config = _conn(vamp_home)
    prospect = _prospect(conn)
    profile_service.set_profile(conn, {"voice_sample": "I write short, no-nonsense emails."})

    system, prompt, schema = pitch_service.build_prompt(conn, prospect)

    assert "no-nonsense" in prompt
    assert schema["context"]["voice_sample"] == "I write short, no-nonsense emails."


def test_draft_pitch_falls_back_on_provider_failure(vamp_home: Path):
    conn, _config = _conn(vamp_home)
    prospect = _prospect(conn)

    result = pitch_service.draft_pitch(conn, _RaisingProvider(), prospect)

    assert result["provider"] == "none"
    assert result["body"]


def test_draft_pitch_reads_local_bio_asset_text(vamp_home: Path, tmp_path: Path):
    conn, config = _conn(vamp_home)
    prospect = _prospect(conn)
    create_asset(
        conn,
        config.home,
        kind="bio",
        name="Bio",
        file_name="bio.txt",
        file_bytes=b"Kaelyn is a pianist and free improviser.",
        ready=True,
    )

    system, prompt, schema = pitch_service.build_prompt(conn, prospect)

    assert "free improviser" in prompt
    assert schema["context"]["bio"] == "Kaelyn is a pianist and free improviser."


def test_draft_pitch_redraft_replaces_latest(vamp_home: Path):
    conn, _config = _conn(vamp_home)
    prospect = _prospect(conn)

    pitch_service.draft_pitch(conn, _FixedProvider({"subject": "first", "body": "body1"}), prospect)
    pitch_service.draft_pitch(
        conn, _FixedProvider({"subject": "second", "body": "body2"}), prospect
    )

    latest = pitch_service.latest_pitch(conn, prospect["id"])
    import json

    assert json.loads(latest["content_json"])["subject"] == "second"
