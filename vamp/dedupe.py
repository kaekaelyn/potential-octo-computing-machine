"""Dedupe: canonical-URL hash + normalized fuzzy (org, title, event-date)
hash — two independent keys, either of which matching an existing lead
counts as a duplicate (PLAN.md §3, Wingman-style).
"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_PARAM_RE = re.compile(r"^(utm_|fbclid|gclid|mc_eid|mc_cid|igshid)", re.IGNORECASE)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def canonical_url(url: str) -> str | None:
    """Normalize a URL for dedupe: lowercase host, strip tracking params,
    drop fragment and trailing slash, force https scheme."""
    if not url:
        return None
    parts = urlsplit(url.strip())
    if not parts.netloc:
        return None
    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parts.path.rstrip("/")
    kept_query = sorted(
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not _TRACKING_PARAM_RE.match(k)
    )
    return urlunsplit(("https", netloc, path, urlencode(kept_query), ""))


def url_hash(url: str | None) -> str | None:
    canon = canonical_url(url) if url else None
    return hashlib.sha256(canon.encode("utf-8")).hexdigest() if canon else None


def _normalize(value: str | None) -> str:
    return _NON_ALNUM_RE.sub(" ", value.lower()).strip() if value else ""


def fuzzy_key(title: str | None, org: str | None, event_date: str | None) -> str:
    """Normalized (org, title, event-date) fuzzy hash."""
    normalized = "|".join([_normalize(org), _normalize(title), _normalize(event_date)])
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def find_duplicate(conn, url_h: str | None, fuzzy_h: str | None):
    """Return an existing lead row matching either hash, or None."""
    if url_h:
        row = conn.execute("SELECT * FROM leads WHERE url_hash = ?", (url_h,)).fetchone()
        if row:
            return row
    if fuzzy_h:
        row = conn.execute("SELECT * FROM leads WHERE dedupe_hash = ?", (fuzzy_h,)).fetchone()
        if row:
            return row
    return None
