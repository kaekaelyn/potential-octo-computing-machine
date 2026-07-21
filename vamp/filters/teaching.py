"""Teaching filter: excludes lesson/instructor/faculty-type postings.

Kaelyn performs; she does not want teaching offers in the feed.
"""

from __future__ import annotations

import re

REASON = "teaching"

_PATTERNS = [
    r"\bpiano\s+(teacher|instructor)s?\b",
    r"\b(voice|vocal|music)\s+(teacher|instructor)s?\b",
    r"\bprivate\s+lessons?\b",
    r"\b(give|teach|teaching)\s+(piano|voice|vocal|music)\s+lessons?\b",
    r"\bteaching\s+(studio|position|job|role|artist)\b",
    r"\b(studio|adjunct)\s+(faculty|instructor)\b",
    r"\badjunct\s+(professor|faculty)\b",
    r"\bfaculty\s+(position|opening|opportunity)\b",
    r"\bmusic\s+tutor(ing)?\b",
    r"\baccepting\s+(new\s+)?students\b",
    r"\blesson\s+plans?\b",
]

_TEACHING_RE = re.compile("|".join(_PATTERNS), re.IGNORECASE)


def check_teaching(text: str) -> str | None:
    return REASON if _TEACHING_RE.search(text) else None
