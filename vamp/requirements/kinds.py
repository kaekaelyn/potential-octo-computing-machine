"""Requirement + asset kind vocabulary (PLAN.md §5).

Requirement kinds are what a posting asks for; asset kinds are what the
vault stores. Most requirement kinds map 1:1 onto an asset kind that can
satisfy them — ``REQUIREMENT_TO_ASSET_KIND`` is that mapping. A few
requirement kinds (in-person audition, cover letter, catch-all "other")
have no corresponding vault asset — they're never "READY", just surfaced
as action items on the lead's checklist.
"""

from __future__ import annotations

# Canonical order matches PLAN.md §5's checklist listing.
REQUIREMENT_KINDS: tuple[str, ...] = (
    "live_video",
    "audio_demo",
    "cv",
    "bio",
    "repertoire_list",
    "references",
    "headshot",
    "epk_link",
    "in_person_audition",
    "cover_letter",
    "other",
)

REQUIREMENT_LABELS: dict[str, str] = {
    "live_video": "live video",
    "audio_demo": "audio demo",
    "cv": "CV/resume",
    "bio": "bio",
    "repertoire_list": "repertoire list",
    "references": "references",
    "headshot": "headshot",
    "epk_link": "EPK/website link",
    "in_person_audition": "in-person audition",
    "cover_letter": "cover letter",
    "other": "other",
}

# Canonical order matches PLAN.md §5's vault listing (rate card/tech rider
# have no corresponding requirement kind — postings rarely ask for them
# directly, but the kit builder still tracks them as assets).
ASSET_KINDS: tuple[str, ...] = (
    "bio",
    "headshot",
    "live_video",
    "audio_demo",
    "repertoire_list",
    "cv",
    "references",
    "tech_rider",
    "rate_card",
    "epk",
)

ASSET_LABELS: dict[str, str] = {
    "bio": "bio",
    "headshot": "headshot",
    "live_video": "live video",
    "audio_demo": "audio demo",
    "repertoire_list": "repertoire list",
    "cv": "CV",
    "references": "references",
    "tech_rider": "tech rider / stage plot",
    "rate_card": "rate card",
    "epk": "EPK",
}

# requirement kind -> asset kind that can satisfy it; None = not
# vault-trackable (an action item, never "READY").
REQUIREMENT_TO_ASSET_KIND: dict[str, str | None] = {
    "live_video": "live_video",
    "audio_demo": "audio_demo",
    "cv": "cv",
    "bio": "bio",
    "repertoire_list": "repertoire_list",
    "references": "references",
    "headshot": "headshot",
    "epk_link": "epk",
    "in_person_audition": None,
    "cover_letter": None,
    "other": None,
}


def is_trackable(requirement_kind: str) -> bool:
    return REQUIREMENT_TO_ASSET_KIND.get(requirement_kind) is not None
