"""Adzuna adapter: salaried/hourly musician jobs, OKC + configurable radius
(PLAN.md §3 Tier A, §12 M2).

Adzuna splits results by query term rather than one combined search, so we
run one request per query and merge, deduping by URL within the adapter
(the runner's own dedupe against the ``leads`` table catches anything that
slips through across polls).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urlencode

import httpx

from vamp.capture.parser import guess_pay
from vamp.sources.base import NotConfiguredError, RawLead

FETCH_TIMEOUT_SECONDS = 10.0
API_BASE = "https://api.adzuna.com/v1/api/jobs"

DEFAULT_QUERIES = ["musician", "pianist", "keyboardist", "accompanist", "music director"]
DEFAULT_WHERE = "Oklahoma City"
DEFAULT_RADIUS_MILES = 25
RESULTS_PER_PAGE = 50

JsonFetcher = Callable[[str], dict]


@dataclass
class AdzunaConfig:
    app_id: str | None
    app_key: str | None
    where: str = DEFAULT_WHERE
    radius_miles: int = DEFAULT_RADIUS_MILES
    queries: list[str] = field(default_factory=lambda: list(DEFAULT_QUERIES))
    country: str = "us"


def _default_fetch_json(url: str) -> dict:
    response = httpx.get(url, timeout=FETCH_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


def _to_raw_lead(job: dict) -> RawLead:
    description = job.get("description") or ""
    salary_min = job.get("salary_min")
    salary_max = job.get("salary_max")
    if salary_min or salary_max:
        pay_min = int(salary_min) if salary_min else None
        pay_max = int(salary_max) if salary_max else pay_min
        pay_kind = "salary"
    else:
        pay_min, pay_max, pay_kind = guess_pay(description)
    return RawLead(
        title=job.get("title") or "Untitled Adzuna listing",
        description=description,
        kind="job",
        org=(job.get("company") or {}).get("display_name"),
        location=(job.get("location") or {}).get("display_name"),
        url=job.get("redirect_url"),
        posted_at=job.get("created"),
        pay_min=pay_min,
        pay_max=pay_max,
        pay_kind=pay_kind,
        raw=job,
    )


class AdzunaAdapter:
    def __init__(self, config: AdzunaConfig, fetch_json: JsonFetcher | None = None):
        self.config = config
        self._fetch_json = fetch_json or _default_fetch_json

    def _search_url(self, query: str) -> str:
        params = {
            "app_id": self.config.app_id,
            "app_key": self.config.app_key,
            "results_per_page": RESULTS_PER_PAGE,
            "what": query,
            "where": self.config.where,
            "distance": self.config.radius_miles,
            "content-type": "application/json",
        }
        return f"{API_BASE}/{self.config.country}/search/1?{urlencode(params)}"

    def fetch(self) -> list[RawLead]:
        if not self.config.app_id or not self.config.app_key:
            raise NotConfiguredError(
                "Adzuna not configured: set ADZUNA_APP_ID and ADZUNA_APP_KEY in ~/.vamp/env"
            )
        leads: list[RawLead] = []
        seen_urls: set[str] = set()
        for query in self.config.queries:
            data = self._fetch_json(self._search_url(query))
            for job in data.get("results", []):
                raw = _to_raw_lead(job)
                if raw.url:
                    if raw.url in seen_urls:
                        continue
                    seen_urls.add(raw.url)
                leads.append(raw)
        return leads
