"""Degree filter: excludes postings that hard-require a music degree with
no "or equivalent experience/training" carve-out (PLAN.md §4).

Heuristic only in M1 (an AI second-opinion pass is M5). A posting is
excluded when some sentence both names a degree and uses requirement
language ("required", "must have", "minimum of"); if the posting anywhere
uses equivalent/comparable-experience language, the wall is considered
opened and the lead is not excluded.
"""

from __future__ import annotations

import re

REASON = "degree-wall"

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_DEGREE_RE = re.compile(
    r"\b(bachelor'?s?|master'?s?|b\.?m\.?|m\.?m\.?|b\.?a\.?|m\.?a\.?|college|university)\s+degree\b"
    r"|\bdegree\s+in\s+music\b",
    re.IGNORECASE,
)
_REQUIRE_RE = re.compile(
    r"\brequired\b|\bmust\s+(have|hold|possess)\b|\bminimum\s+of\b|\bis\s+required\b",
    re.IGNORECASE,
)
_EQUIVALENT_RE = re.compile(
    r"\bor\s+equivalent\b|\bor\s+comparable\b|\bequivalent\s+(experience|training)\b"
    r"|\bcomparable\s+(experience|training)\b",
    re.IGNORECASE,
)


def check_degree(text: str) -> str | None:
    if _EQUIVALENT_RE.search(text):
        return None
    for sentence in _SENTENCE_SPLIT_RE.split(text):
        if _DEGREE_RE.search(sentence) and _REQUIRE_RE.search(sentence):
            return REASON
    return None
