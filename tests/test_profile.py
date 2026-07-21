from __future__ import annotations

from pathlib import Path

from vamp import db as vamp_db
from vamp.config import load_config
from vamp.profile import service as profile_service


def _conn(vamp_home: Path):
    config = load_config(home=vamp_home)
    return vamp_db.get_connection(config.db_path)


def test_get_profile_returns_defaults_when_unset(vamp_home: Path):
    conn = _conn(vamp_home)

    profile = profile_service.get_profile(conn)

    assert profile["display_name"] == "Kaelyn"
    assert profile["voice_sample"] == ""


def test_set_profile_persists_and_round_trips(vamp_home: Path):
    conn = _conn(vamp_home)

    profile_service.set_profile(
        conn,
        {
            "display_name": "K. Lyn",
            "instrument": "keyboardist",
            "home_area": "Norman, OK",
            "voice_sample": "warm and direct",
        },
    )

    profile = profile_service.get_profile(conn)
    assert profile["display_name"] == "K. Lyn"
    assert profile["voice_sample"] == "warm and direct"


def test_set_profile_upserts_not_duplicates(vamp_home: Path):
    conn = _conn(vamp_home)

    profile_service.set_profile(conn, {"display_name": "First"})
    profile_service.set_profile(conn, {"display_name": "Second"})

    rows = conn.execute("SELECT * FROM profile WHERE key = 'display_name'").fetchall()
    assert len(rows) == 1
    assert rows[0]["value"] == "Second"
