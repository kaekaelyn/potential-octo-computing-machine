from __future__ import annotations

from pathlib import Path

from vamp.sources.rss import RssAdapter, RssConfig

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_FEED_BYTES = (FIXTURES / "sample_feed.xml").read_bytes()


def _fake_fetch_bytes(url: str) -> bytes:
    assert url == "https://example.org/feed.xml"
    return SAMPLE_FEED_BYTES


def test_fetch_parses_entries_into_raw_leads():
    adapter = RssAdapter(
        RssConfig(feed_url="https://example.org/feed.xml"), fetch_bytes=_fake_fetch_bytes
    )

    leads = adapter.fetch()

    assert len(leads) == 2
    accompanist = next(lead for lead in leads if "Accompanist" in lead.title)
    assert accompanist.url == "https://example.org/opportunities/accompanist-wanted"
    assert "rehearsal accompanist" in accompanist.description
    assert accompanist.kind == "other"
    assert accompanist.posted_at


def test_falls_back_to_feed_title_as_org():
    adapter = RssAdapter(
        RssConfig(feed_url="https://example.org/feed.xml"), fetch_bytes=_fake_fetch_bytes
    )

    leads = adapter.fetch()

    assert all(lead.org == "OKC Arts Council Opportunities" for lead in leads)


def test_configured_name_overrides_feed_title_as_org():
    adapter = RssAdapter(
        RssConfig(feed_url="https://example.org/feed.xml", name="Arts Council RSS"),
        fetch_bytes=_fake_fetch_bytes,
    )

    leads = adapter.fetch()

    assert all(lead.org == "Arts Council RSS" for lead in leads)


def test_raw_json_is_serializable():
    import json

    adapter = RssAdapter(
        RssConfig(feed_url="https://example.org/feed.xml"), fetch_bytes=_fake_fetch_bytes
    )

    for lead in adapter.fetch():
        json.dumps(lead.raw)  # must not raise
