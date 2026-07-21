"""Requirements parser: heuristic keyword/pattern pass decomposing a lead's
text into the checklist kinds from PLAN.md §5. An AI extraction pass that
merges with this heuristic pass is M5 — this module must stand on its own
(CLAUDE.md: "every AI feature must work (degraded) when no provider is
available").

Matching runs sentence-by-sentence so one sentence can't accidentally
donate a phrase to an unrelated kind (e.g. "video" in one sentence and
"audition" in the next shouldn't combine into "video audition").
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from vamp.requirements.kinds import REQUIREMENT_KINDS

_WHITESPACE_RE = re.compile(r"\s+")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_SNIPPET_LIMIT = 160


@dataclass
class ParsedRequirement:
    kind: str
    detail: str  # matched phrase / verbatim sentence


# Order doesn't matter for matching (each sentence is tested against every
# pattern), but it fixes iteration order for readability.
_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    (
        "live_video",
        re.compile(
            r"live\s+video"
            r"|video\s+of\s+(?:you|yourself)\s+(?:performing|playing)"
            r"|performance\s+video"
            r"|video\s+audition"
            r"|link\s+to\s+(?:a\s+)?video"
            r"|youtube\s+link",
            re.IGNORECASE,
        ),
    ),
    (
        "audio_demo",
        re.compile(
            r"audio\s+(?:demo|sample|recording)"
            r"|demo\s+(?:reel|recording|track)"
            r"|sound\s*cloud\s+link"
            r"|mp3\s+(?:file|recording)",
            re.IGNORECASE,
        ),
    ),
    ("cv", re.compile(r"\bcv\b|r[ée]sum[ée]", re.IGNORECASE)),
    ("bio", re.compile(r"artist\s+bio|short\s+bio|\bbio(?:graphy)?\b", re.IGNORECASE)),
    (
        "repertoire_list",
        re.compile(
            r"repertoire\s+list|song\s+list|set\s*list|list\s+of\s+(?:songs|repertoire)",
            re.IGNORECASE,
        ),
    ),
    (
        "references",
        re.compile(
            r"(?:\d+|two|three|four)\s+references"
            r"|professional\s+references"
            r"|references?\s+(?:required|upon\s+request|list|available)",
            re.IGNORECASE,
        ),
    ),
    ("headshot", re.compile(r"headshots?|professional\s+photo", re.IGNORECASE)),
    (
        "epk_link",
        re.compile(
            r"\bepk\b"
            r"|electronic\s+press\s+kit"
            r"|press\s+kit"
            r"|website\s+link"
            r"|link\s+to\s+your\s+website"
            r"|portfolio\s+(?:link|website)",
            re.IGNORECASE,
        ),
    ),
    (
        "in_person_audition",
        re.compile(
            r"in[- ]person\s+audition"
            r"|live\s+audition"
            r"|audition\s+in\s+person"
            r"|schedule\s+an\s+audition"
            r"|audition\s+(?:day|process|date)"
            r"|\bcallback\b",
            re.IGNORECASE,
        ),
    ),
    ("cover_letter", re.compile(r"cover\s+letter|letter\s+of\s+interest", re.IGNORECASE)),
)

_SUBMISSION_HINT_RE = re.compile(
    r"please\s+(?:also\s+)?(?:submit|send|include|provide|attach)"
    r"|must\s+(?:submit|send|include|provide)"
    r"|be\s+sure\s+to\s+(?:submit|send|include)",
    re.IGNORECASE,
)


def _snippet(sentence: str) -> str:
    sentence = re.sub(r"\s+", " ", sentence).strip()
    if len(sentence) <= _SNIPPET_LIMIT:
        return sentence
    return sentence[: _SNIPPET_LIMIT - 1].rstrip() + "…"


def parse_requirements(text: str) -> list[ParsedRequirement]:
    """Decompose ``text`` into requirement checklist items. Never raises;
    an empty/None text yields an empty list. Returns at most one
    requirement per kind, ordered per ``REQUIREMENT_KINDS``."""
    normalized = _WHITESPACE_RE.sub(" ", text or "").strip()
    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(normalized) if s.strip()]

    found: dict[str, str] = {}
    for sentence in sentences:
        for kind, pattern in _PATTERNS:
            if kind in found:
                continue
            match = pattern.search(sentence)
            if match:
                found[kind] = _snippet(sentence)

    for sentence in sentences:
        if "other" in found:
            break
        if not _SUBMISSION_HINT_RE.search(sentence):
            continue
        if any(pattern.search(sentence) for _, pattern in _PATTERNS):
            continue
        found["other"] = _snippet(sentence)

    return [
        ParsedRequirement(kind=kind, detail=found[kind])
        for kind in REQUIREMENT_KINDS
        if kind in found
    ]
