"""Source adapter protocol: ``fetch() -> list[RawLead]`` (PLAN.md §3/§12 M2).

Every adapter is independent and polled by the runner (``vamp/sources/
runner.py``), which is responsible for isolating failures — an adapter is
free to just raise on any error (network, bad config, policy refusal); the
runner catches it, records it on that source's row, and moves on to the
next source untouched.

``RawLead`` deliberately mirrors ``vamp.capture.parser.ParsedLead``'s
attributes so ``leads.service.create_lead`` accepts either one unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class RawLead:
    title: str
    description: str = ""
    kind: str = "other"  # gig|job|competition|open_mic|showcase|other
    org: str | None = None
    location: str | None = None
    url: str | None = None
    event_date: str | None = None
    deadline: str | None = None
    posted_at: str | None = None
    pay_min: int | None = None
    pay_max: int | None = None
    pay_kind: str = "unknown"  # flat|hourly|salary|tips|unpaid|unknown
    needs_review: bool = False
    raw: dict = field(default_factory=dict)


class SourceAdapter(Protocol):
    def fetch(self) -> list[RawLead]: ...


class NotConfiguredError(Exception):
    """Raised when an adapter is missing required config (e.g. an API key)."""


class BlockedDomainError(Exception):
    """Raised when a target falls on the hard-coded capture-only blocklist."""


class RobotsDisallowedError(Exception):
    """Raised when robots.txt disallows fetching the target URL."""
