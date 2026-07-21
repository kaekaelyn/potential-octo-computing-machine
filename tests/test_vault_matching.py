from __future__ import annotations

from pathlib import Path

from vamp import db as vamp_db
from vamp.capture.parser import ParsedLead
from vamp.config import load_config
from vamp.leads import service as leads_service
from vamp.vault import assets as assets_service
from vamp.vault.matching import lead_status, status_for_leads, unlock_report


def _conn(vamp_home: Path):
    config = load_config(home=vamp_home)
    return vamp_db.get_connection(config.db_path), config


def _lead(conn, description: str, title: str = "Church pianist"):
    lead_id, created, _ = leads_service.create_lead(
        conn, ParsedLead(title=title, description=description, pay_kind="salary", pay_min=100)
    )
    assert created
    return lead_id


def test_lead_gets_requirements_parsed_on_capture(vamp_home: Path):
    conn, _config = _conn(vamp_home)
    lead_id = _lead(conn, "Please send a resume and three references.")

    rows = conn.execute("SELECT kind FROM requirements WHERE lead_id = ?", (lead_id,)).fetchall()

    assert {r["kind"] for r in rows} == {"cv", "references"}


def test_lead_becomes_ready_once_matching_ready_asset_exists(vamp_home: Path):
    conn, config = _conn(vamp_home)
    lead_id = _lead(conn, "Please send a short bio.")

    assert lead_status(conn, lead_id)["ready"] is False

    assets_service.create_asset(
        conn, config.home, kind="bio", name="150-word bio", tags="", ready=True
    )

    status = lead_status(conn, lead_id)
    assert status["ready"] is True
    assert status["checklist"][0]["satisfied"] is True


def test_asset_going_not_ready_unmatches_requirement(vamp_home: Path):
    conn, config = _conn(vamp_home)
    lead_id = _lead(conn, "Please send a short bio.")
    asset_id = assets_service.create_asset(
        conn, config.home, kind="bio", name="150-word bio", tags="", ready=True
    )
    assert lead_status(conn, lead_id)["ready"] is True

    assets_service.toggle_ready(conn, asset_id)  # now not-ready

    assert lead_status(conn, lead_id)["ready"] is False


def test_non_trackable_requirements_never_block_ready(vamp_home: Path):
    conn, _config = _conn(vamp_home)
    lead_id = _lead(conn, "Please schedule an in-person audition.")

    status = lead_status(conn, lead_id)
    # in_person_audition has no matching asset kind — no trackable
    # requirements at all, so this lead is neither READY nor "missing".
    assert status["has_requirements"] is False
    assert status["ready"] is False
    assert status["checklist"][0]["trackable"] is False


def test_status_for_leads_batches_without_missing_any(vamp_home: Path):
    conn, config = _conn(vamp_home)
    ready_lead = _lead(conn, "Please send a short bio.", title="Ready one")
    assets_service.create_asset(conn, config.home, kind="bio", name="Bio", tags="", ready=True)
    missing_lead = _lead(conn, "Please send a headshot.", title="Missing one")

    statuses = status_for_leads(conn, [ready_lead, missing_lead])

    assert statuses[ready_lead]["ready"] is True
    assert statuses[missing_lead]["ready"] is False
    assert statuses[missing_lead]["missing_labels"] == ["headshot"]


def test_unlock_report_ranks_by_leads_unlocked(vamp_home: Path):
    conn, _config = _conn(vamp_home)
    _lead(conn, "Please send a headshot.", title="A")
    _lead(conn, "Please send a headshot.", title="B")
    _lead(conn, "Please send a short bio.", title="C")

    report = unlock_report(conn)

    assert report["total_open"] == 3
    assert report["entries"][0]["asset_kind"] == "headshot"
    assert report["entries"][0]["lead_count"] == 2


def test_unlock_report_excludes_booked_and_excluded_leads(vamp_home: Path):
    conn, _config = _conn(vamp_home)
    lead_id = _lead(conn, "Please send a headshot.")
    conn.execute("UPDATE leads SET state = 'booked' WHERE id = ?", (lead_id,))
    conn.commit()

    report = unlock_report(conn)

    assert report["total_open"] == 0
    assert report["entries"] == []
