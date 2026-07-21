from __future__ import annotations

import json
from pathlib import Path

import pytest

from vamp.sources.base import NotConfiguredError
from vamp.sources.usajobs import UsajobsAdapter, UsajobsConfig

FIXTURES = Path(__file__).parent / "fixtures"
USAJOBS_RESPONSE = json.loads((FIXTURES / "usajobs_response.json").read_text())


def _fake_fetch_json(captured_headers: list[dict]):
    def fetch_json(url: str, headers: dict) -> dict:
        captured_headers.append(headers)
        return USAJOBS_RESPONSE

    return fetch_json


def test_fetch_maps_military_band_posting():
    headers: list[dict] = []
    adapter = UsajobsAdapter(
        UsajobsConfig(api_key="key", email="kaelyn@example.com", keywords=["musician"]),
        fetch_json=_fake_fetch_json(headers),
    )

    leads = adapter.fetch()

    assert len(leads) == 1
    lead = leads[0]
    assert lead.title == "Musician (Keyboard)"
    assert lead.org == "U.S. Army"
    assert lead.location == "Fort Sill, Oklahoma"
    assert lead.url == "https://www.usajobs.gov/job/700000001"
    assert lead.deadline == "2026-08-01"
    assert lead.pay_kind == "salary"
    assert lead.pay_min == 45000
    assert lead.pay_max == 55000
    assert lead.kind == "job"

    assert headers[0]["Authorization-Key"] == "key"
    assert headers[0]["User-Agent"] == "kaelyn@example.com"


def test_dedupes_across_keywords():
    headers: list[dict] = []
    adapter = UsajobsAdapter(
        UsajobsConfig(
            api_key="key", email="kaelyn@example.com", keywords=["musician", "band", "keyboard"]
        ),
        fetch_json=_fake_fetch_json(headers),
    )

    leads = adapter.fetch()

    assert len(leads) == 1
    assert len(headers) == 3


def test_missing_credentials_raises_not_configured():
    adapter = UsajobsAdapter(UsajobsConfig(api_key=None, email=None))

    with pytest.raises(NotConfiguredError):
        adapter.fetch()
