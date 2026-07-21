"""Hard filters: pure functions, text in -> reason code(s) out.

Each filter is independent and default-on (PLAN.md §4). ``run_hard_filters``
runs all three and returns every reason code that fired, so a lead can be
excluded for more than one reason at once.
"""

from __future__ import annotations

from vamp.filters.degree import REASON as DEGREE_REASON
from vamp.filters.degree import check_degree
from vamp.filters.pay_to_play import REASON as PAY_TO_PLAY_REASON
from vamp.filters.pay_to_play import check_pay_to_play
from vamp.filters.teaching import REASON as TEACHING_REASON
from vamp.filters.teaching import check_teaching

REASON_CHIP = {
    TEACHING_REASON: "−teaching",
    DEGREE_REASON: "−degree-wall",
    PAY_TO_PLAY_REASON: "−pay-to-play",
}


def run_hard_filters(text: str) -> list[str]:
    """Return every reason code triggered by ``text`` (may be empty)."""
    checks = (check_teaching(text), check_degree(text), check_pay_to_play(text))
    return [reason for reason in checks if reason]
