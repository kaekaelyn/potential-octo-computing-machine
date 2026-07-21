"""Route-level coverage for the one-tap AI actions wired into the leads,
prospects, and kit blueprints (PLAN.md §12 M5 acceptance: "one-tap pitch
drafts"). Every test strips PATH so it can never shell out to a real
``claude`` binary — see ``vamp.ai.provider.ClaudeProvider`` for why a
missing binary is a normal, tested degradation path, not an error."""

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


def _no_real_claude_on_path(monkeypatch, tmp_path: Path) -> None:
    empty_bin_dir = tmp_path / "empty-bin"
    empty_bin_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("PATH", str(empty_bin_dir))


def _insert_lead(config, **overrides):
    defaults = dict(
        kind="gig",
        dedupe_hash="fuzzy-1",
        url_hash=None,
        title="Solo piano, Friday night",
        description="Solo piano for cocktail hour.",
        state="inbox",
        excluded_reason=None,
    )
    defaults.update(overrides)
    conn = vamp_db.get_connection(config.db_path)
    try:
        cur = conn.execute(
            """INSERT INTO leads (kind, dedupe_hash, url_hash, title, description, state,
                                   excluded_reason)
               VALUES (:kind, :dedupe_hash, :url_hash, :title, :description, :state,
                       :excluded_reason)""",
            defaults,
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def test_score_now_button_scores_and_shows_result(vamp_home: Path, tmp_path: Path, monkeypatch):
    _no_real_claude_on_path(monkeypatch, tmp_path)
    client, config = _client(vamp_home)
    lead_id = _insert_lead(config)

    response = client.post(f"/leads/{lead_id}/score")
    assert response.status_code == 302

    detail = client.get(f"/leads/{lead_id}").get_data(as_text=True)
    assert "/100" in detail
    assert "none" in detail  # scorer shown on the page


def test_degree_review_button_on_excluded_lead(vamp_home: Path, tmp_path: Path, monkeypatch):
    _no_real_claude_on_path(monkeypatch, tmp_path)
    client, config = _client(vamp_home)
    lead_id = _insert_lead(
        config,
        title="Church pianist",
        description="Bachelor's degree in Music required.",
        state="excluded",
        excluded_reason="degree-wall",
    )

    response = client.post(f"/leads/{lead_id}/degree-review")
    assert response.status_code == 302

    detail = client.get(f"/leads/{lead_id}").get_data(as_text=True)
    assert "second opinion" in detail.lower()
    # Heuristic (no provider) always stands pat.
    assert "Agrees with the exclusion" in detail


def test_degree_review_button_rejects_non_degree_lead(vamp_home: Path, tmp_path: Path, monkeypatch):
    _no_real_claude_on_path(monkeypatch, tmp_path)
    client, config = _client(vamp_home)
    lead_id = _insert_lead(config, state="inbox")

    response = client.post(f"/leads/{lead_id}/degree-review")
    assert response.status_code == 302
    detail = client.get(f"/leads/{lead_id}")
    assert detail.status_code == 200


def _insert_prospect(config, **overrides):
    from vamp.prospects.pipeline import create_prospect

    fields = {"name": "The Grand Hotel", "category": "hotel", "angle": "lobby grand"}
    fields.update(overrides)
    conn = vamp_db.get_connection(config.db_path)
    try:
        return create_prospect(conn, fields)
    finally:
        conn.close()


def test_draft_pitch_button_on_prospect_detail(vamp_home: Path, tmp_path: Path, monkeypatch):
    _no_real_claude_on_path(monkeypatch, tmp_path)
    client, config = _client(vamp_home)
    prospect_id = _insert_prospect(config)

    response = client.post(f"/prospects/{prospect_id}/draft-pitch")
    assert response.status_code == 302

    detail = client.get(f"/prospects/{prospect_id}").get_data(as_text=True)
    assert "Grand Hotel" in detail
    assert "Redraft pitch" in detail


def test_draft_followup_button_on_prospect_detail(vamp_home: Path, tmp_path: Path, monkeypatch):
    _no_real_claude_on_path(monkeypatch, tmp_path)
    client, config = _client(vamp_home)
    prospect_id = _insert_prospect(config)

    response = client.post(f"/prospects/{prospect_id}/draft-followup")
    assert response.status_code == 302

    detail = client.get(f"/prospects/{prospect_id}").get_data(as_text=True)
    assert "Redraft follow-up" in detail


def test_draft_sub_availability_button(vamp_home: Path, tmp_path: Path, monkeypatch):
    _no_real_claude_on_path(monkeypatch, tmp_path)
    client, config = _client(vamp_home)
    prospect_id = _insert_prospect(config)

    response = client.post(
        f"/prospects/{prospect_id}/draft-sub-availability", data={"date": "March 9"}
    )
    assert response.status_code == 302

    detail = client.get(f"/prospects/{prospect_id}").get_data(as_text=True)
    assert "March 9" in detail


def test_draft_bio_button_on_kit_page(vamp_home: Path, tmp_path: Path, monkeypatch):
    _no_real_claude_on_path(monkeypatch, tmp_path)
    client, _config = _client(vamp_home)

    response = client.post("/kit/draft-bio")
    assert response.status_code == 302

    body = client.get("/kit").get_data(as_text=True)
    assert "Redraft bio" in body
    assert "50 words" in body


def test_profile_edit_round_trip(vamp_home: Path):
    client, _config = _client(vamp_home)

    response = client.post(
        "/profile",
        data={
            "display_name": "K. Lyn",
            "instrument": "keyboardist",
            "home_area": "Norman, OK",
            "voice_sample": "Warm, direct, no fluff.",
        },
    )
    assert response.status_code == 302

    body = client.get("/profile").get_data(as_text=True)
    assert "K. Lyn" in body
    assert "Warm, direct, no fluff." in body
