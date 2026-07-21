from __future__ import annotations

from pathlib import Path

from vamp import db as vamp_db
from vamp.app import create_app
from vamp.config import load_config


def _client(vamp_home: Path):
    config = load_config(home=vamp_home)
    app = create_app(config)
    app.testing = True
    return app.test_client(), config


def _insert_lead(config, **overrides):
    defaults = dict(
        kind="gig",
        dedupe_hash="fuzzy-1",
        url_hash=None,
        url=None,
        title="Solo piano, Friday night",
        org="Vast",
        pay_kind="flat",
        pay_min=250,
        pay_max=250,
        state="inbox",
        needs_review=0,
    )
    defaults.update(overrides)
    conn = vamp_db.get_connection(config.db_path)
    try:
        cur = conn.execute(
            """INSERT INTO leads (kind, dedupe_hash, url_hash, url, title, org, pay_kind,
                                   pay_min, pay_max, state, needs_review)
               VALUES (:kind, :dedupe_hash, :url_hash, :url, :title, :org, :pay_kind,
                       :pay_min, :pay_max, :state, :needs_review)""",
            defaults,
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def test_paying_lead_appears_on_paying_shelf_only(vamp_home: Path):
    client, config = _client(vamp_home)
    _insert_lead(config, title="Paid gig", pay_kind="flat")

    body = client.get("/leads").get_data(as_text=True)

    assert "Paid gig" in body.split("Stepping-stones")[0]


def test_unpaid_lead_never_sorts_into_paying_shelf(vamp_home: Path):
    client, config = _client(vamp_home)
    _insert_lead(config, title="Open mic", pay_kind="unpaid", pay_min=None, pay_max=None)

    body = client.get("/leads").get_data(as_text=True)
    paying_section, _, stepping_section = body.partition("Stepping-stones")

    assert "Open mic" not in paying_section
    assert "Open mic" in stepping_section


def test_unknown_and_tips_pay_kinds_also_land_on_stepping_stones(vamp_home: Path):
    client, config = _client(vamp_home)
    _insert_lead(config, title="Tips gig", pay_kind="tips", pay_min=None, pay_max=None)
    _insert_lead(config, title="Mystery gig", pay_kind="unknown", pay_min=None, pay_max=None)

    body = client.get("/leads").get_data(as_text=True)
    paying_section, _, stepping_section = body.partition("Stepping-stones")

    assert "Tips gig" not in paying_section
    assert "Mystery gig" not in paying_section
    assert "Tips gig" in stepping_section
    assert "Mystery gig" in stepping_section


def test_excluded_lead_is_hidden_from_inbox_and_shown_on_excluded_shelf(vamp_home: Path):
    client, config = _client(vamp_home)
    _insert_lead(config, title="Teaching gig", state="excluded", excluded_reason="teaching")

    inbox = client.get("/leads").get_data(as_text=True)
    excluded = client.get("/leads/excluded").get_data(as_text=True)

    assert "Teaching gig" not in inbox
    assert "Teaching gig" in excluded
    assert "teaching" in excluded.lower()


def test_restore_moves_lead_back_to_inbox(vamp_home: Path):
    client, config = _client(vamp_home)
    lead_id = _insert_lead(
        config, title="Restorable gig", state="excluded", excluded_reason="teaching"
    )

    response = client.post(f"/leads/{lead_id}/restore")

    assert response.status_code == 302
    inbox = client.get("/leads").get_data(as_text=True)
    excluded = client.get("/leads/excluded").get_data(as_text=True)
    assert "Restorable gig" in inbox
    assert "Restorable gig" not in excluded


def test_finish_by_hand_update_clears_needs_review_and_reruns_filters(vamp_home: Path):
    client, config = _client(vamp_home)
    lead_id = _insert_lead(
        config, title="Shared lead", description="", pay_kind="unknown", needs_review=1
    )

    response = client.post(
        f"/leads/{lead_id}",
        data={
            "title": "Piano teacher wanted",
            "description": "Now offering private lessons in NW OKC.",
            "pay_kind": "flat",
            "pay_min": "40",
            "pay_max": "40",
        },
    )

    assert response.status_code == 302
    excluded = client.get("/leads/excluded").get_data(as_text=True)
    assert "Piano teacher wanted" in excluded
    detail = client.get(f"/leads/{lead_id}").get_data(as_text=True)
    assert "finish by hand" not in detail.lower()  # needs_review cleared


def test_detail_404s_for_missing_lead(vamp_home: Path):
    client, _config = _client(vamp_home)
    response = client.get("/leads/999")
    assert response.status_code == 404
