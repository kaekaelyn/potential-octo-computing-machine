from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from vamp import db as vamp_db
from vamp.config import load_config
from vamp.gigs import pipeline as gigs_pipeline
from vamp.notify.digest import digest_headline, morning_digest
from vamp.prospects import cadence as prospects_cadence
from vamp.prospects import pipeline as prospects_pipeline
from vamp.vault import assets as assets_service

NOW = datetime(2026, 7, 20, 8, 0, 0)  # a Monday


def _conn(vamp_home: Path):
    return vamp_db.get_connection(load_config(home=vamp_home).db_path)


def _insert_lead(conn, **overrides):
    defaults = dict(
        kind="gig",
        dedupe_hash="fuzzy-1",
        url_hash=None,
        title="Solo piano, Friday night",
        description="First Baptist needs a pianist. Send a CV.",
        org="Vast",
        pay_kind="flat",
        pay_min=250,
        pay_max=250,
        state="inbox",
        first_seen_at=NOW.strftime("%Y-%m-%d %H:%M:%S"),
    )
    defaults.update(overrides)
    cols = list(defaults.keys())
    placeholders = ", ".join(f":{c}" for c in cols)
    cur = conn.execute(f"INSERT INTO leads ({', '.join(cols)}) VALUES ({placeholders})", defaults)
    conn.commit()
    return cur.lastrowid


def test_counts_only_paying_leads_within_the_lookback_window(vamp_home: Path):
    conn = _conn(vamp_home)
    try:
        _insert_lead(conn, dedupe_hash="a", pay_kind="flat")
        _insert_lead(conn, dedupe_hash="b", pay_kind="tips")  # not paying — excluded
        _insert_lead(
            conn,
            dedupe_hash="c",
            pay_kind="flat",
            first_seen_at="2020-01-01 00:00:00",  # outside the 24h window
        )
        _insert_lead(conn, dedupe_hash="d", pay_kind="flat", state="excluded")

        digest = morning_digest(conn, now=NOW)
        assert digest["summary"]["new_paying"] == 1
    finally:
        conn.close()


def test_ready_count_reflects_vault_matching(vamp_home: Path):
    config = load_config(home=vamp_home)
    conn = vamp_db.get_connection(config.db_path)
    try:
        lead_id = _insert_lead(
            conn, dedupe_hash="ready-lead", description="Please send a resume to apply."
        )
        # The raw insert above bypasses leads.service.create_lead (which
        # would normally parse requirements on the way in) — do it by hand,
        # the same way the app does on capture.
        from vamp.vault.matching import sync_requirements

        sync_requirements(conn, lead_id, "Please send a resume to apply.")
        assets_service.create_asset(conn, config.home, kind="cv", name="My CV", ready=True)
        sync_requirements(conn, lead_id, "Please send a resume to apply.")

        digest = morning_digest(conn, now=NOW)
        assert digest["summary"]["new_paying"] == 1
        assert digest["summary"]["new_paying_ready"] == 1
    finally:
        conn.close()


def test_follow_ups_due_counts_prospect_and_chase_unpaid(vamp_home: Path):
    conn = _conn(vamp_home)
    try:
        pid = prospects_pipeline.create_prospect(conn, {"name": "The Jones Assembly"})
        prospects_cadence.schedule_follow_ups(
            conn, pid, "The Jones Assembly", from_time=datetime(2020, 1, 1)
        )
        gid = gigs_pipeline.create_gig(conn, {"venue": "Vast", "date": "2020-01-01"})
        gigs_pipeline.set_state(conn, gid, "played", now=datetime(2020, 1, 1))
        conn.commit()

        digest = morning_digest(conn, now=NOW)
        # 2 prospect follow-ups (+7d/+21d, both long overdue from 2020) + 1
        # gig chase-unpaid reminder.
        assert digest["summary"]["follow_ups_due"] == 3
    finally:
        conn.close()


def test_tonight_events_only_include_going_events_occurring_today(vamp_home: Path):
    conn = _conn(vamp_home)
    try:
        today_weekday = NOW.strftime("%A").lower()
        conn.execute(
            "INSERT INTO scene_events (name, venue, cadence_json, going) VALUES (?, ?, ?, 1)",
            (
                "Open Mic Night",
                "The Deli",
                json.dumps({"freq": "weekly", "weekday": today_weekday}),
            ),
        )
        conn.execute(
            "INSERT INTO scene_events (name, venue, cadence_json, going) VALUES (?, ?, ?, 0)",
            ("Not Going", "Elsewhere", json.dumps({"freq": "weekly", "weekday": today_weekday})),
        )
        other_weekday = "sunday" if today_weekday != "sunday" else "monday"
        conn.execute(
            "INSERT INTO scene_events (name, venue, cadence_json, going) VALUES (?, ?, ?, 1)",
            ("Different Day", "Nowhere", json.dumps({"freq": "weekly", "weekday": other_weekday})),
        )
        conn.commit()

        digest = morning_digest(conn, now=NOW)
        names = [e["name"] for e in digest["tonight_events"]]
        assert names == ["Open Mic Night"]
    finally:
        conn.close()


def test_headline_combines_all_parts():
    digest = {
        "summary": {
            "new_paying": 2,
            "new_paying_ready": 1,
            "follow_ups_due": 3,
            "tonight_events": 1,
        },
        "tonight_events": [{"name": "Open Mic Night", "venue": "The Deli"}],
    }
    headline = digest_headline(digest)
    assert "2 new paying leads (1 READY)" in headline
    assert "3 follow-ups due" in headline
    assert "Open Mic Night at The Deli tonight" in headline


def test_headline_quiet_when_nothing_to_report():
    digest = {
        "summary": {
            "new_paying": 0,
            "new_paying_ready": 0,
            "follow_ups_due": 0,
            "tonight_events": 0,
        },
        "tonight_events": [],
    }
    assert digest_headline(digest) == "Quiet morning — nothing new. Open Vamp anyway."


def test_headline_singular_lead_and_follow_up():
    digest = {
        "summary": {
            "new_paying": 1,
            "new_paying_ready": 0,
            "follow_ups_due": 1,
            "tonight_events": 0,
        },
        "tonight_events": [],
    }
    headline = digest_headline(digest)
    assert "1 new paying lead," in headline
    assert "1 follow-up due" in headline
