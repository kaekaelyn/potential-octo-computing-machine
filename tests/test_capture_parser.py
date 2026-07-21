from __future__ import annotations

from pathlib import Path

import pytest

from vamp.capture.parser import (
    capture,
    extract_url,
    guess_pay,
    parse_heuristic,
    parse_jsonld,
    parse_opengraph,
    parse_shared_text,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


# --------------------------------------------------------------- JSON-LD --


def test_parse_jsonld_job_posting():
    parsed = parse_jsonld(_fixture("jsonld_job_posting.html"))
    assert parsed is not None
    assert parsed.title == "Church Pianist"
    assert parsed.org == "First Church OKC"
    assert parsed.location == "Oklahoma City, OK"
    assert parsed.kind == "job"
    assert parsed.pay_min == 300
    assert parsed.pay_max == 400
    assert parsed.deadline == "2026-09-01"
    assert "or equivalent experience" in parsed.description
    assert parsed.needs_review is False


def test_parse_jsonld_event():
    parsed = parse_jsonld(_fixture("jsonld_event.html"))
    assert parsed is not None
    assert "Songwriter Round" in parsed.title
    assert parsed.org == "The Blue Door"
    assert parsed.event_date == "2026-09-12T20:00"
    assert parsed.needs_review is False


def test_parse_jsonld_returns_none_when_absent():
    assert parse_jsonld(_fixture("opengraph_post.html")) is None


# ------------------------------------------------------------- OpenGraph --


def test_parse_opengraph():
    parsed = parse_opengraph(_fixture("opengraph_post.html"))
    assert parsed is not None
    assert parsed.title == "Open mic tonight at The Deli"
    assert parsed.org == "The Deli Norman"
    assert parsed.pay_kind == "tips"


def test_parse_opengraph_returns_none_without_og_title():
    assert parse_opengraph(_fixture("heuristic_only.html")) is None


# -------------------------------------------------------------- heuristic --


def test_parse_heuristic_from_title_and_first_paragraph():
    parsed = parse_heuristic(_fixture("heuristic_only.html"))
    assert parsed is not None
    assert "Ceremony Pianist" in parsed.title
    assert parsed.pay_min == 200
    assert parsed.pay_kind == "flat"


# ------------------------------------------------------------------- pay --


@pytest.mark.parametrize(
    "text,expected_kind",
    [
        ("This gig pays $250 flat for the night.", "flat"),
        ("We pay $25/hr, 3-hour minimum.", "hourly"),
        ("This is a salaried position.", "salary"),
        ("Tips only, no guarantee.", "tips"),
        ("Unpaid, but great exposure!", "unpaid"),
        ("Message us for details.", "unknown"),
    ],
)
def test_guess_pay_kind(text, expected_kind):
    _, _, kind = guess_pay(text)
    assert kind == expected_kind


def test_guess_pay_range():
    lo, hi, kind = guess_pay("Pay is $200-$300 depending on set length.")
    assert (lo, hi, kind) == (200, 300, "flat")


# ------------------------------------------------------- share-text path --


def test_extract_url_strips_trailing_punctuation():
    assert (
        extract_url("check this out: https://example.com/post/1.") == "https://example.com/post/1"
    )


def test_parse_shared_text_never_raises_and_needs_review():
    parsed = parse_shared_text("")
    assert parsed.needs_review is True
    assert parsed.title  # never blank


def test_parse_shared_text_extracts_embedded_url_and_pay():
    text = _fixture("share_text_with_url.txt")
    parsed = parse_shared_text(text)
    assert parsed.needs_review is True
    assert parsed.url is not None
    assert parsed.url.startswith("https://www.facebook.com/groups/okcmusicianscircle")
    assert parsed.pay_min == 200
    assert "keyboardist" in parsed.description.lower()


# ------------------------------------------------------ capture() (top) --


def test_capture_uses_jsonld_when_fetch_succeeds():
    def fake_fetch(url: str) -> str:
        return _fixture("jsonld_job_posting.html")

    parsed = capture(url="https://firstchurchokc.example/jobs/pianist", fetch=fake_fetch)
    assert parsed.title == "Church Pianist"
    assert parsed.needs_review is False


def test_capture_falls_back_to_shared_text_on_fetch_failure():
    def failing_fetch(url: str) -> str:
        raise TimeoutError("Facebook blocked the fetch")

    text = _fixture("share_text_with_url.txt")
    parsed = capture(url=None, text=text, fetch=failing_fetch)
    assert parsed.needs_review is True
    assert parsed.title
    assert parsed.description == text.strip()


def test_capture_falls_back_on_non_html_response():
    def image_fetch(url: str) -> str:
        raise ValueError("unsupported content-type: 'image/jpeg'")

    parsed = capture(
        url="https://example.com/flyer.jpg", text="Flyer for Saturday's gig", fetch=image_fetch
    )
    assert parsed.needs_review is True
    assert parsed.url == "https://example.com/flyer.jpg"


def test_capture_never_raises_when_fetch_and_text_both_empty():
    parsed = capture(url=None, text=None, fetch=lambda url: (_ for _ in ()).throw(RuntimeError()))
    assert parsed.needs_review is True
    assert parsed.title
