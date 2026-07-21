"""Generic RSS/Atom adapter — the escape hatch for church-job boards, arts
orgs, and anything else with a feed (PLAN.md §3 Tier A, §12 M2).
"""

from __future__ import annotations

import io
from collections.abc import Callable
from dataclasses import dataclass

import feedparser
import httpx
from bs4 import BeautifulSoup

from vamp.capture.parser import guess_pay
from vamp.sources.base import RawLead

FETCH_TIMEOUT_SECONDS = 10.0

BytesFetcher = Callable[[str], bytes]


@dataclass
class RssConfig:
    feed_url: str
    name: str | None = None


def _default_fetch_bytes(url: str) -> bytes:
    response = httpx.get(
        url,
        timeout=FETCH_TIMEOUT_SECONDS,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (compatible; VampRSS/0.1)"},
    )
    response.raise_for_status()
    return response.content


def _strip_html(value: str | None) -> str:
    if not value:
        return ""
    return BeautifulSoup(value, "html.parser").get_text(" ").strip()


def _posted_at(entry) -> str | None:
    # feedparser maps a missing `updated` to `published` internally (with a
    # deprecation warning) — checking membership first avoids ever
    # triggering that fallback ourselves.
    if "published" in entry:
        return entry.get("published")
    if "updated" in entry:
        return entry.get("updated")
    return None


def _entry_to_raw_lead(entry, feed_org: str | None) -> RawLead:
    description = _strip_html(entry.get("summary") or entry.get("description"))
    pay_min, pay_max, pay_kind = guess_pay(description)
    posted_at = _posted_at(entry)
    # feedparser entries carry non-JSON-serializable values (struct_time,
    # nested link dicts) — keep raw_json to the plain scalar fields.
    raw = {
        "title": entry.get("title"),
        "link": entry.get("link"),
        "id": entry.get("id"),
        "posted_at": posted_at,
        "summary": entry.get("summary"),
    }
    return RawLead(
        title=entry.get("title") or "Untitled feed item",
        description=description,
        kind="other",
        org=feed_org,
        url=entry.get("link"),
        posted_at=posted_at,
        pay_min=pay_min,
        pay_max=pay_max,
        pay_kind=pay_kind,
        raw=raw,
    )


class RssAdapter:
    def __init__(self, config: RssConfig, fetch_bytes: BytesFetcher | None = None):
        self.config = config
        self._fetch_bytes = fetch_bytes or _default_fetch_bytes

    def fetch(self) -> list[RawLead]:
        content = self._fetch_bytes(self.config.feed_url)
        parsed = feedparser.parse(io.BytesIO(content))
        feed_org = self.config.name or parsed.feed.get("title")
        return [_entry_to_raw_lead(entry, feed_org) for entry in parsed.entries]
