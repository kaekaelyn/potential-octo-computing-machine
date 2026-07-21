"""Capture parsing: JSON-LD (JobPosting/Event) -> OpenGraph -> heuristic
HTML -> shared-text "finish by hand" fallback.

This module never raises. A capture always produces a ``ParsedLead`` —
if the URL can't be fetched or parsed (Facebook blocks fetching often;
PLAN.md §3/§13), the shared text itself becomes the lead body and
``needs_review`` is set so the UI shows a pre-filled finish-by-hand form
instead of an error.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx
from bs4 import BeautifulSoup

FETCH_TIMEOUT_SECONDS = 6.0

_URL_RE = re.compile(r"https?://\S+")
_TRAILING_PUNCT_RE = re.compile(r"[)\]}>.,;!?\"']+$")

_UNPAID_RE = re.compile(
    r"\bunpaid\b|\bno\s+pay\b|\bno\s+compensation\b|\bvolunteer(s|ing)?\b|\bfor\s+exposure\b",
    re.IGNORECASE,
)
_HOURLY_HINT_RE = re.compile(r"/\s*hr\b|/\s*hour\b|per\s+hour|hourly", re.IGNORECASE)
_SALARY_RE = re.compile(r"\bsalary\b|\bsalaried\b", re.IGNORECASE)
_TIPS_RE = re.compile(r"\btips?\b", re.IGNORECASE)
_MONEY_RE = re.compile(r"\$\s?([\d,]+(?:\.\d+)?)\s*(?:[-–to]+\s*\$?\s?([\d,]+(?:\.\d+)?))?")

_JOB_TYPES = {"JobPosting"}
_EVENT_TYPES = {"Event", "MusicEvent", "SocialEvent", "TheaterEvent", "Festival"}


@dataclass
class ParsedLead:
    title: str
    description: str = ""
    kind: str = "other"  # gig|job|competition|open_mic|showcase|other
    org: str | None = None
    location: str | None = None
    url: str | None = None
    event_date: str | None = None
    deadline: str | None = None
    pay_min: int | None = None
    pay_max: int | None = None
    pay_kind: str = "unknown"  # flat|hourly|salary|tips|unpaid|unknown
    needs_review: bool = False
    raw: dict = field(default_factory=dict)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = re.sub(r"\s+", " ", value).strip()
    return value or None


def _strip_html(value: str | None) -> str | None:
    if not value:
        return None
    return _clean(BeautifulSoup(value, "html.parser").get_text(" "))


def extract_url(text: str) -> str | None:
    match = _URL_RE.search(text or "")
    if not match:
        return None
    return _TRAILING_PUNCT_RE.sub("", match.group(0))


def guess_pay(text: str) -> tuple[int | None, int | None, str]:
    """Heuristic pay extraction used for the text/finish-by-hand path."""
    if _UNPAID_RE.search(text):
        return None, None, "unpaid"
    money = _MONEY_RE.search(text)
    if money:
        lo = int(float(money.group(1).replace(",", "")))
        hi = int(float(money.group(2).replace(",", ""))) if money.group(2) else lo
        kind = "hourly" if _HOURLY_HINT_RE.search(text) else "flat"
        return min(lo, hi), max(lo, hi), kind
    if _SALARY_RE.search(text):
        return None, None, "salary"
    if _TIPS_RE.search(text):
        return None, None, "tips"
    return None, None, "unknown"


# ---------------------------------------------------------------- JSON-LD --


def _jsonld_blocks(soup: BeautifulSoup) -> list[dict]:
    blocks: list[dict] = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or tag.get_text() or "null")
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, list):
            blocks.extend(d for d in data if isinstance(d, dict))
        elif isinstance(data, dict):
            graph = data.get("@graph")
            if isinstance(graph, list):
                blocks.extend(d for d in graph if isinstance(d, dict))
            else:
                blocks.append(data)
    return blocks


def _type_in(obj: dict, names: set[str]) -> bool:
    obj_type = obj.get("@type")
    if isinstance(obj_type, list):
        return any(t in names for t in obj_type)
    return obj_type in names


def _org_name(value) -> str | None:
    if isinstance(value, dict):
        return _clean(value.get("name"))
    if isinstance(value, str):
        return _clean(value)
    return None


def _location_text(value) -> str | None:
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, dict):
        name = _clean(value.get("name"))
        address = value.get("address")
        if isinstance(address, dict):
            parts = [address.get(k) for k in ("addressLocality", "addressRegion")]
            addr_text = ", ".join(p for p in parts if p)
        elif isinstance(address, str):
            addr_text = address
        else:
            addr_text = None
        return name or _clean(addr_text)
    if isinstance(value, str):
        return _clean(value)
    return None


def _pay_from_jobposting(obj: dict) -> tuple[int | None, int | None, str]:
    salary = obj.get("baseSalary")
    if isinstance(salary, dict):
        value = salary.get("value")
        if isinstance(value, dict):
            unit = (value.get("unitText") or "").upper()
            kind = "hourly" if unit == "HOUR" else "salary" if unit in ("YEAR", "MONTH") else "flat"
            lo = value.get("minValue") or value.get("value")
            hi = value.get("maxValue") or value.get("value")
            if lo is not None or hi is not None:
                lo_i = int(lo) if lo is not None else None
                hi_i = int(hi) if hi is not None else lo_i
                return lo_i, hi_i, kind
    if obj.get("employmentType") in ("VOLUNTEER",):
        return None, None, "unpaid"
    return guess_pay(_strip_html(obj.get("description")) or "")


def _from_jobposting(obj: dict) -> ParsedLead:
    pay_min, pay_max, pay_kind = _pay_from_jobposting(obj)
    return ParsedLead(
        title=_clean(obj.get("title")) or "Untitled job posting",
        description=_strip_html(obj.get("description")) or "",
        kind="job",
        org=_org_name(obj.get("hiringOrganization")),
        location=_location_text(obj.get("jobLocation")),
        url=_clean(obj.get("url")),
        deadline=_clean(obj.get("validThrough")),
        pay_min=pay_min,
        pay_max=pay_max,
        pay_kind=pay_kind,
        raw=obj,
    )


def _from_event(obj: dict) -> ParsedLead:
    description = _strip_html(obj.get("description")) or ""
    is_free = obj.get("isAccessibleForFree") is True
    offers = obj.get("offers")
    pay_min, pay_max, pay_kind = guess_pay(description)
    if is_free and pay_kind == "unknown":
        pay_kind = "unpaid"
    return ParsedLead(
        title=_clean(obj.get("name")) or "Untitled event",
        description=description,
        kind="showcase" if "showcase" in (obj.get("name") or "").lower() else "gig",
        org=_org_name(obj.get("organizer")) or _location_text(obj.get("location")),
        location=_location_text(obj.get("location")),
        url=_clean(obj.get("url")),
        event_date=_clean(obj.get("startDate")),
        pay_min=pay_min,
        pay_max=pay_max,
        pay_kind=pay_kind,
        raw={**obj, "offers": offers} if offers else obj,
    )


def parse_jsonld(html: str) -> ParsedLead | None:
    soup = BeautifulSoup(html, "html.parser")
    for obj in _jsonld_blocks(soup):
        if _type_in(obj, _JOB_TYPES):
            return _from_jobposting(obj)
        if _type_in(obj, _EVENT_TYPES):
            return _from_event(obj)
    return None


# ------------------------------------------------------------- OpenGraph --


def parse_opengraph(html: str) -> ParsedLead | None:
    soup = BeautifulSoup(html, "html.parser")

    def og(prop: str) -> str | None:
        tag = soup.find("meta", attrs={"property": f"og:{prop}"})
        return _clean(tag.get("content")) if tag else None

    title = og("title")
    if not title:
        return None
    description = og("description")
    if not description:
        meta_desc = soup.find("meta", attrs={"name": "description"})
        description = _clean(meta_desc.get("content")) if meta_desc else None
    description = description or ""
    pay_min, pay_max, pay_kind = guess_pay(description)
    return ParsedLead(
        title=title,
        description=description,
        org=og("site_name"),
        url=og("url"),
        pay_min=pay_min,
        pay_max=pay_max,
        pay_kind=pay_kind,
    )


# -------------------------------------------------------------- heuristic --


def parse_heuristic(html: str) -> ParsedLead | None:
    soup = BeautifulSoup(html, "html.parser")
    title_tag = soup.find("title")
    title = _clean(title_tag.get_text()) if title_tag else None
    if not title:
        return None
    paragraph = soup.find("p")
    description = _clean(paragraph.get_text(" ")) if paragraph else ""
    description = description or ""
    pay_min, pay_max, pay_kind = guess_pay(description)
    return ParsedLead(
        title=title, description=description, pay_min=pay_min, pay_max=pay_max, pay_kind=pay_kind
    )


# --------------------------------------------------- finish-by-hand path --


def parse_shared_text(
    text: str | None, title_hint: str | None = None, url_hint: str | None = None
) -> ParsedLead:
    """Always succeeds: builds a "finish by hand" lead straight from the
    text an app shared to Vamp (or a paste-box submission)."""
    text = text or ""
    url = url_hint or extract_url(text)
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    title = _clean(title_hint) or (first_line[:160] if first_line else None) or url or "Shared lead"
    pay_min, pay_max, pay_kind = guess_pay(text)
    return ParsedLead(
        title=title,
        description=text.strip(),
        url=url,
        pay_min=pay_min,
        pay_max=pay_max,
        pay_kind=pay_kind,
        needs_review=True,
    )


# ------------------------------------------------------------------ fetch --

Fetcher = Callable[[str], str]


def _default_fetch(url: str) -> str:
    response = httpx.get(
        url,
        timeout=FETCH_TIMEOUT_SECONDS,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (compatible; VampCapture/0.1)"},
    )
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if "html" not in content_type and "xml" not in content_type:
        raise ValueError(f"unsupported content-type: {content_type!r}")
    return response.text


def capture(
    url: str | None = None,
    text: str | None = None,
    title: str | None = None,
    fetch: Fetcher | None = None,
) -> ParsedLead:
    """Top-level capture entry point. Never raises.

    Tries, in order: fetch + JSON-LD, fetch + OpenGraph, fetch + heuristic
    HTML. If there is no URL, or the fetch/parse fails for any reason,
    falls back to parsing the shared text directly (finish-by-hand).
    """
    text = text or ""
    target_url = (url or extract_url(text) or "").strip() or None
    fetcher = fetch or _default_fetch

    if target_url:
        try:
            html = fetcher(target_url)
        except Exception:
            html = None
        if html:
            parsed = parse_jsonld(html) or parse_opengraph(html) or parse_heuristic(html)
            if parsed:
                if not parsed.url:
                    parsed.url = target_url
                if title and not parsed.raw.get("_share_title"):
                    parsed.raw = {**parsed.raw, "_share_title": title}
                return parsed

    return parse_shared_text(text or title, title_hint=title, url_hint=target_url)
