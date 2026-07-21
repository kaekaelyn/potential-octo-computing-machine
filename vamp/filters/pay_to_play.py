"""Pay-to-play filter: flags "exposure" scams — required ticket sales,
"bring 20 people", buy-ins, and pay-to-perform showcases (PLAN.md §4).
"""

from __future__ import annotations

import re

REASON = "pay-to-play"

_PATTERNS = [
    r"\bpay[- ]to[- ]play\b",
    r"\bsell\s+(a\s+minimum\s+of\s+)?\d+\s+tickets?\b",
    r"\brequired\s+to\s+sell\s+\d*\s*tickets?\b",
    r"\bticket\s+quota\b",
    r"\bbring\s+\d+\s+(people|guests|friends)\b",
    r"\bbuy[- ]in\s+(of\s+)?\$?\d+\b",
    r"\bpurchase\s+(a\s+)?table\b",
    r"\b\$\d+\s+(entry|registration|application)\s+fee\s+to\s+perform\b",
    r"\bperformers?\s+must\s+purchase\b",
    r"\bpay\s+\$?\d+\s+to\s+perform\b",
]

_PAY_TO_PLAY_RE = re.compile("|".join(_PATTERNS), re.IGNORECASE)


def check_pay_to_play(text: str) -> str | None:
    return REASON if _PAY_TO_PLAY_RE.search(text) else None
