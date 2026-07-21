"""The personal rate floor (PLAN.md §8): a single number, set from researched
OKC-market rate ranges, that flags paying leads and not-yet-played gigs
quoted below it with a `−below-floor` chip — unless the row is flagged
`strategic` (a deliberate below-floor booking, e.g. a retirement-circuit
foothold or a favor for a referring planner). The chip is a nudge, never a
block; nothing here excludes or filters anything.
"""

from __future__ import annotations

import sqlite3

from vamp.profile import service as profile_service

BELOW_FLOOR_CHIP = "−below-floor"


def get_rate_floor(conn: sqlite3.Connection) -> float | None:
    raw = profile_service.get_profile(conn).get("rate_floor")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def is_below_floor(amount: float | None, floor: float | None) -> bool:
    """True when ``amount`` is a known figure strictly below ``floor``.

    A missing amount or an unset floor is never "below" — there's nothing
    to flag without both numbers.
    """
    if floor is None or amount is None:
        return False
    return amount < floor
