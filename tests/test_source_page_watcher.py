from __future__ import annotations

from pathlib import Path

import pytest

from vamp.sources.base import BlockedDomainError, RobotsDisallowedError
from vamp.sources.page_watcher import MIN_INTERVAL_SECONDS, PageWatchConfig, PageWatcherAdapter

FIXTURES = Path(__file__).parent / "fixtures"
PAGE_V1 = (FIXTURES / "page_watch_v1.html").read_text()
PAGE_V2 = (FIXTURES / "page_watch_v2.html").read_text()
ROBOTS_ALLOW = (FIXTURES / "robots_allow.txt").read_text()
ROBOTS_DISALLOW = (FIXTURES / "robots_disallow.txt").read_text()

PAGE_URL = "https://arts.example.org/opportunities"


def _fetch(page_html: str, robots_txt: str = ROBOTS_ALLOW):
    def fetch(url: str) -> str:
        if url.endswith("robots.txt"):
            return robots_txt
        assert url == PAGE_URL
        return page_html

    return fetch


# ------------------------------------------------------------- validation --


@pytest.mark.parametrize("domain", ["facebook.com", "www.instagram.com", "m.craigslist.org"])
def test_blocklisted_domain_refused_at_construction(domain):
    with pytest.raises(BlockedDomainError):
        PageWatchConfig(url=f"https://{domain}/some-group", name="blocked")


def test_interval_below_24h_rejected():
    with pytest.raises(ValueError):
        PageWatchConfig(url=PAGE_URL, name="test", interval_seconds=3600)


def test_css_mode_requires_selector():
    with pytest.raises(ValueError):
        PageWatchConfig(url=PAGE_URL, name="test", mode="css", selector=None)


def test_unknown_mode_rejected():
    with pytest.raises(ValueError):
        PageWatchConfig(url=PAGE_URL, name="test", mode="poll")


# ------------------------------------------------------------------ robots --


def test_robots_disallow_raises_and_skips_fetch():
    fetched_page = []

    def fetch(url: str) -> str:
        if url.endswith("robots.txt"):
            return ROBOTS_DISALLOW
        fetched_page.append(url)
        return PAGE_V1

    config = PageWatchConfig(url=PAGE_URL, name="Arts Council")
    adapter = PageWatcherAdapter(config, last_hash=None, fetch=fetch)

    with pytest.raises(RobotsDisallowedError):
        adapter.fetch()
    assert fetched_page == []


def test_robots_allow_proceeds():
    config = PageWatchConfig(url=PAGE_URL, name="Arts Council")
    adapter = PageWatcherAdapter(config, last_hash=None, fetch=_fetch(PAGE_V1))

    leads = adapter.fetch()

    assert leads == []  # first poll just seeds the baseline
    assert adapter.state_to_persist


def test_missing_robots_txt_treated_as_allowed():
    def fetch(url: str) -> str:
        if url.endswith("robots.txt"):
            raise RuntimeError("404 Not Found")
        return PAGE_V1

    config = PageWatchConfig(url=PAGE_URL, name="Arts Council")
    adapter = PageWatcherAdapter(config, last_hash=None, fetch=fetch)

    leads = adapter.fetch()
    assert leads == []


# --------------------------------------------------------------- diff mode --


def test_first_poll_seeds_baseline_without_emitting_a_lead():
    config = PageWatchConfig(url=PAGE_URL, name="Arts Council")
    adapter = PageWatcherAdapter(config, last_hash=None, fetch=_fetch(PAGE_V1))

    leads = adapter.fetch()

    assert leads == []
    assert adapter.state_to_persist is not None


def test_unchanged_content_emits_no_lead():
    config = PageWatchConfig(url=PAGE_URL, name="Arts Council")
    seed = PageWatcherAdapter(config, last_hash=None, fetch=_fetch(PAGE_V1))
    seed.fetch()
    baseline_hash = seed.state_to_persist

    adapter = PageWatcherAdapter(config, last_hash=baseline_hash, fetch=_fetch(PAGE_V1))
    leads = adapter.fetch()

    assert leads == []


def test_changed_content_emits_a_needs_review_lead():
    config = PageWatchConfig(url=PAGE_URL, name="Arts Council")
    seed = PageWatcherAdapter(config, last_hash=None, fetch=_fetch(PAGE_V1))
    seed.fetch()
    baseline_hash = seed.state_to_persist

    adapter = PageWatcherAdapter(config, last_hash=baseline_hash, fetch=_fetch(PAGE_V2))
    leads = adapter.fetch()

    assert len(leads) == 1
    lead = leads[0]
    assert lead.needs_review is True
    assert lead.url == PAGE_URL
    assert "Festival musician application" in lead.description
    assert adapter.state_to_persist != baseline_hash


# ---------------------------------------------------------------- css mode --


def test_css_selector_mode_watches_only_the_selected_element():
    config = PageWatchConfig(
        url=PAGE_URL, name="Arts Council", mode="css", selector="#opportunities"
    )
    seed = PageWatcherAdapter(config, last_hash=None, fetch=_fetch(PAGE_V1))
    seed.fetch()
    baseline_hash = seed.state_to_persist

    adapter = PageWatcherAdapter(config, last_hash=baseline_hash, fetch=_fetch(PAGE_V2))
    leads = adapter.fetch()

    assert len(leads) == 1
    assert "No open calls" not in leads[0].description
    assert "Festival musician application" in leads[0].description


# ---------------------------------------------------------- runtime guard --


def test_fetch_reasserts_blocklist_even_if_config_mutated_after_construction():
    config = PageWatchConfig(url=PAGE_URL, name="Arts Council")
    adapter = PageWatcherAdapter(config, last_hash=None, fetch=_fetch(PAGE_V1))
    config.url = "https://www.facebook.com/groups/okcmusicianscircle/"

    with pytest.raises(BlockedDomainError):
        adapter.fetch()


def test_default_min_interval_is_24_hours():
    assert MIN_INTERVAL_SECONDS == 24 * 3600
