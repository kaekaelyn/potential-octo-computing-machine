from __future__ import annotations

import json
from pathlib import Path

import pytest

from vamp.sources.adzuna import AdzunaAdapter, AdzunaConfig
from vamp.sources.base import NotConfiguredError

FIXTURES = Path(__file__).parent / "fixtures"
ADZUNA_RESPONSE = json.loads((FIXTURES / "adzuna_response.json").read_text())


def _fake_fetch_json(seen_urls: list[str]):
    def fetch_json(url: str) -> dict:
        seen_urls.append(url)
        return ADZUNA_RESPONSE

    return fetch_json


def test_fetch_returns_raw_leads_for_each_query():
    seen: list[str] = []
    adapter = AdzunaAdapter(
        AdzunaConfig(app_id="id123", app_key="key456", queries=["musician", "pianist"]),
        fetch_json=_fake_fetch_json(seen),
    )

    leads = adapter.fetch()

    # Same two listings returned for both queries, deduped by URL.
    assert len(leads) == 2
    assert len(seen) == 2
    titles = {lead.title for lead in leads}
    assert titles == {"Hotel Lobby Pianist", "Church Accompanist"}


def test_maps_salary_fields_to_pay():
    seen: list[str] = []
    adapter = AdzunaAdapter(
        AdzunaConfig(app_id="id123", app_key="key456", queries=["musician"]),
        fetch_json=_fake_fetch_json(seen),
    )

    leads = {lead.title: lead for lead in adapter.fetch()}

    pianist = leads["Hotel Lobby Pianist"]
    assert pianist.pay_kind == "salary"
    assert pianist.pay_min == 32000
    assert pianist.pay_max == 38000
    assert pianist.org == "Skirvin Hilton Hotel"
    assert pianist.location == "Oklahoma City, OK"
    assert pianist.kind == "job"

    accompanist = leads["Church Accompanist"]
    assert accompanist.pay_kind == "unknown"


def test_search_url_includes_where_and_radius():
    captured_urls: list[str] = []

    def fetch_json(url: str) -> dict:
        captured_urls.append(url)
        return {"results": []}

    adapter = AdzunaAdapter(
        AdzunaConfig(
            app_id="id123",
            app_key="key456",
            where="Oklahoma City",
            radius_miles=40,
            queries=["musician"],
        ),
        fetch_json=fetch_json,
    )
    adapter.fetch()

    assert len(captured_urls) == 1
    url = captured_urls[0]
    assert "where=Oklahoma+City" in url
    assert "distance=40" in url
    assert "what=musician" in url


def test_missing_credentials_raises_not_configured():
    adapter = AdzunaAdapter(AdzunaConfig(app_id=None, app_key=None))

    with pytest.raises(NotConfiguredError):
        adapter.fetch()


def test_default_queries_cover_the_plan_terms():
    from vamp.sources.adzuna import DEFAULT_QUERIES

    for term in ("musician", "pianist", "keyboardist", "accompanist", "music director"):
        assert term in DEFAULT_QUERIES
