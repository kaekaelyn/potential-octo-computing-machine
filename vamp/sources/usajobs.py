"""USAJOBS adapter: military band / musician series postings (PLAN.md §3
Tier A — "Army/Air Force band keyboardist posts: salaried, benefits, real
auditions", §12 M2).

USAJOBS requires an ``Authorization-Key`` header plus a ``User-Agent`` set
to the email address registered for the key; both live in ``~/.vamp/env``
alongside the key itself.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urlencode

import httpx

from vamp.sources.base import NotConfiguredError, RawLead

FETCH_TIMEOUT_SECONDS = 10.0
API_BASE = "https://data.usajobs.gov/api/search"

DEFAULT_KEYWORDS = ["musician", "band", "music director"]
# USAJOBS occupational series 1051 ("Music Specialist") covers military band
# musician billets; narrows results without excluding keyword-only matches.
MUSIC_SPECIALIST_SERIES = "1051"

JsonFetcher = Callable[[str, dict[str, str]], dict]


@dataclass
class UsajobsConfig:
    api_key: str | None
    email: str | None
    keywords: list[str] = field(default_factory=lambda: list(DEFAULT_KEYWORDS))
    job_category_code: str | None = MUSIC_SPECIALIST_SERIES
    location_name: str | None = None
    radius_miles: int | None = None


def _default_fetch_json(url: str, headers: dict[str, str]) -> dict:
    response = httpx.get(url, headers=headers, timeout=FETCH_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


def _pay_from_remuneration(descriptor: dict) -> tuple[int | None, int | None, str]:
    remuneration = descriptor.get("PositionRemuneration") or []
    if not remuneration:
        return None, None, "unknown"
    first = remuneration[0]
    try:
        lo = int(float(first.get("MinimumRange") or 0)) or None
        hi = int(float(first.get("MaximumRange") or 0)) or None
    except (TypeError, ValueError):
        lo = hi = None
    interval = (first.get("RateIntervalCode") or "").lower()
    kind = "hourly" if "hour" in interval else "salary" if "year" in interval else "flat"
    if lo is None and hi is None:
        return None, None, "unknown"
    return lo, hi or lo, kind


def _to_raw_lead(descriptor: dict) -> RawLead:
    pay_min, pay_max, pay_kind = _pay_from_remuneration(descriptor)
    details = descriptor.get("UserArea", {}).get("Details", {})
    description = details.get("JobSummary") or descriptor.get("QualificationSummary") or ""
    return RawLead(
        title=descriptor.get("PositionTitle") or "Untitled USAJOBS listing",
        description=description,
        kind="job",
        org=descriptor.get("OrganizationName") or descriptor.get("DepartmentName"),
        location=descriptor.get("PositionLocationDisplay"),
        url=descriptor.get("PositionURI"),
        posted_at=descriptor.get("PublicationStartDate"),
        deadline=descriptor.get("ApplicationCloseDate"),
        pay_min=pay_min,
        pay_max=pay_max,
        pay_kind=pay_kind,
        raw=descriptor,
    )


class UsajobsAdapter:
    def __init__(self, config: UsajobsConfig, fetch_json: JsonFetcher | None = None):
        self.config = config
        self._fetch_json = fetch_json or _default_fetch_json

    def _headers(self) -> dict[str, str]:
        return {
            "Host": "data.usajobs.gov",
            "User-Agent": self.config.email or "",
            "Authorization-Key": self.config.api_key or "",
        }

    def _search_url(self, keyword: str) -> str:
        params: dict[str, str] = {"Keyword": keyword}
        if self.config.job_category_code:
            params["JobCategoryCode"] = self.config.job_category_code
        if self.config.location_name:
            params["LocationName"] = self.config.location_name
        if self.config.radius_miles:
            params["Radius"] = str(self.config.radius_miles)
        return f"{API_BASE}?{urlencode(params)}"

    def fetch(self) -> list[RawLead]:
        if not self.config.api_key or not self.config.email:
            raise NotConfiguredError(
                "USAJOBS not configured: set USAJOBS_API_KEY and USAJOBS_EMAIL in ~/.vamp/env"
            )
        leads: list[RawLead] = []
        seen_urls: set[str] = set()
        headers = self._headers()
        for keyword in self.config.keywords:
            data = self._fetch_json(self._search_url(keyword), headers)
            items = data.get("SearchResult", {}).get("SearchResultItems", [])
            for item in items:
                descriptor = item.get("MatchedObjectDescriptor", {})
                raw = _to_raw_lead(descriptor)
                if raw.url:
                    if raw.url in seen_urls:
                        continue
                    seen_urls.add(raw.url)
                leads.append(raw)
        return leads
