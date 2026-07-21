"""The polite page-watcher: CSS-selector or whole-page-diff mode, for pages
with no feed (arts-council opportunity pages, venue "auditions" pages,
festival application pages — PLAN.md §3 Tier A, §12 M2).

Two independent safety rails, both enforced at config time *and* again in
``fetch()`` in case a config is mutated after construction:

- **Domain blocklist:** facebook/instagram/craigslist/indeed/linkedin are
  capture-only platforms per CLAUDE.md's hard rules — share-to-Vamp is the
  only supported path, never automated polling.
- **robots.txt:** checked on every fetch; disallowed pages raise instead
  of being polled.

Per-page interval is enforced to be >= 24h (PLAN.md §3).
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from vamp.sources.base import BlockedDomainError, RawLead, RobotsDisallowedError

FETCH_TIMEOUT_SECONDS = 10.0
MIN_INTERVAL_SECONDS = 24 * 3600
USER_AGENT = "VampPageWatcher/0.1 (local, single-user; respects robots.txt)"

# Hard-coded refusal: capture-only platforms Vamp is never allowed to
# automate (CLAUDE.md hard rules). Share-to-Vamp is the only supported path.
BLOCKED_DOMAINS = ("facebook.com", "instagram.com", "craigslist.org", "indeed.com", "linkedin.com")

Fetcher = Callable[[str], str]


def _default_fetch(url: str) -> str:
    response = httpx.get(
        url,
        timeout=FETCH_TIMEOUT_SECONDS,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    return response.text


def _host_of(url: str) -> str:
    host = urlsplit(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def is_blocked_domain(url: str) -> bool:
    host = _host_of(url)
    return any(host == blocked or host.endswith("." + blocked) for blocked in BLOCKED_DOMAINS)


@dataclass
class PageWatchConfig:
    url: str
    name: str
    mode: str = "diff"  # "diff" | "css"
    selector: str | None = None
    interval_seconds: int = MIN_INTERVAL_SECONDS

    def __post_init__(self) -> None:
        if is_blocked_domain(self.url):
            raise BlockedDomainError(
                f"refusing to watch {self.url}: capture (share-to-Vamp) is the only "
                "supported path for this domain"
            )
        if self.mode not in ("diff", "css"):
            raise ValueError(f"unknown page-watcher mode: {self.mode!r}")
        if self.mode == "css" and not self.selector:
            raise ValueError("css mode requires a selector")
        if self.interval_seconds < MIN_INTERVAL_SECONDS:
            raise ValueError(
                f"page-watcher interval must be >= {MIN_INTERVAL_SECONDS}s (24h), "
                f"got {self.interval_seconds}s"
            )


class PageWatcherAdapter:
    """Polls one page for changes.

    ``state_to_persist`` is set after a successful fetch (whether or not a
    lead was emitted this time) so the runner can save the new content hash
    for the next poll; only meaningful after ``fetch()`` has been called.
    """

    def __init__(
        self,
        config: PageWatchConfig,
        last_hash: str | None = None,
        fetch: Fetcher | None = None,
    ):
        self.config = config
        self.last_hash = last_hash
        self.state_to_persist: str | None = None
        self._fetch = fetch or _default_fetch

    def _check_robots(self) -> None:
        parts = urlsplit(self.config.url)
        robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
        try:
            robots_text = self._fetch(robots_url)
        except Exception:
            return  # no robots.txt, or unreachable -> treat as allowed
        parser = RobotFileParser()
        parser.parse(robots_text.splitlines())
        if not parser.can_fetch(USER_AGENT, self.config.url):
            raise RobotsDisallowedError(f"robots.txt disallows fetching {self.config.url}")

    def _extract_content(self, html: str) -> tuple[str, str]:
        soup = BeautifulSoup(html, "html.parser")
        if self.config.mode == "css":
            selected = soup.select(self.config.selector)
            content = "\n".join(el.get_text(" ", strip=True) for el in selected)
        else:
            content = soup.get_text(" ", strip=True)
        title_tag = soup.find("title")
        page_title = title_tag.get_text(strip=True) if title_tag else self.config.name
        return content, page_title

    def fetch(self) -> list[RawLead]:
        if is_blocked_domain(self.config.url):
            raise BlockedDomainError(f"refusing to watch blocklisted domain: {self.config.url}")
        self._check_robots()

        html = self._fetch(self.config.url)
        content, page_title = self._extract_content(html)
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        self.state_to_persist = content_hash

        if self.last_hash is None:
            return []  # first poll: seed the baseline, nothing to alert on yet
        if content_hash == self.last_hash:
            return []
        return [
            RawLead(
                title=f"{self.config.name} changed: {page_title}",
                description=content[:2000],
                url=self.config.url,
                kind="other",
                needs_review=True,
            )
        ]
