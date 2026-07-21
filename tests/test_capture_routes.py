from __future__ import annotations

from pathlib import Path

from vamp.app import create_app
from vamp.config import load_config

FIXTURES = Path(__file__).parent / "fixtures"


def _client(vamp_home: Path):
    config = load_config(home=vamp_home)
    app = create_app(config)
    app.testing = True
    return app.test_client()


def test_paste_text_capture_creates_a_finish_by_hand_lead(vamp_home: Path):
    client = _client(vamp_home)
    text = (FIXTURES / "posting_clean_paid.txt").read_text()

    response = client.post("/capture", data={"text": text})

    assert response.status_code == 302
    assert response.headers["Location"] == "/leads/1"
    detail = client.get("/leads/1")
    assert detail.status_code == 200
    body = detail.get_data(as_text=True)
    assert "Vast" in body


def test_paste_url_only_falls_back_when_fetch_fails(vamp_home: Path, monkeypatch):
    client = _client(vamp_home)

    def failing_fetch(url: str) -> str:
        raise TimeoutError("blocked")

    # Never live HTTP in tests: patch the default fetcher so this proves
    # the fallback path without touching the network.
    monkeypatch.setattr("vamp.capture.parser._default_fetch", failing_fetch)

    response = client.post("/capture", data={"url": "https://facebook.com/events/999"})

    assert response.status_code == 302
    detail = client.get(response.headers["Location"])
    assert detail.status_code == 200
    assert "finish by hand" in detail.get_data(as_text=True).lower()


def test_capture_with_neither_url_nor_text_shows_error(vamp_home: Path):
    client = _client(vamp_home)

    response = client.post("/capture", data={})

    assert response.status_code == 302
    assert response.headers["Location"] == "/capture"
    follow = client.get("/capture")
    assert "paste a url or some text" in follow.get_data(as_text=True).lower()


def test_teaching_posting_capture_lands_on_excluded_shelf(vamp_home: Path):
    client = _client(vamp_home)
    text = (FIXTURES / "posting_teaching.txt").read_text()

    client.post("/capture", data={"text": text})

    inbox = client.get("/leads").get_data(as_text=True)
    assert "Piano Teacher" not in inbox
    excluded = client.get("/leads/excluded").get_data(as_text=True)
    assert "Piano Teacher" in excluded
    assert "teaching" in excluded.lower()


def test_share_target_endpoint_accepts_web_share_payload(vamp_home: Path):
    client = _client(vamp_home)

    response = client.post(
        "/capture/share",
        data={
            "title": "Great gig!",
            "text": (FIXTURES / "share_text_with_url.txt").read_text(),
            "url": "",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].startswith("/leads/")


def test_dedupe_prevents_duplicate_lead_on_recapture(vamp_home: Path):
    client = _client(vamp_home)
    text = (FIXTURES / "posting_clean_paid.txt").read_text()

    first = client.post("/capture", data={"text": text})
    second = client.post("/capture", data={"text": text})

    assert first.headers["Location"] == second.headers["Location"]
