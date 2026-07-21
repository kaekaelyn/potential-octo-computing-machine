"""Next-date computation from ``scene_events.cadence_json`` (PLAN.md §7/§12
M6): pure functions, no I/O, matching the small structured recurrence shapes
seeded in ``seeds/scene_events.yaml`` —

    {"freq": "monthly", "week": 1, "weekday": "friday", ...}   # 1st Friday
    {"freq": "weekly", "weekday": null, "time": null}          # night TBD
    {"freq": "annual", "month": 4, ...}                        # late April
    {"freq": "annual", "apply_opens": "01-02", "apply_closes": "03-02"}
    {"freq": "bimonthly"}                                      # no anchor

Anything with a missing weekday/month/window is honestly "unknown" (returns
None) rather than guessing a date — the same no-fabrication discipline as
the M4 seed data itself.
"""

from __future__ import annotations

from datetime import date, timedelta

WEEKDAY_NAMES: dict[str, int] = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

_MONTH_NAMES = {
    1: "January",
    2: "February",
    3: "March",
    4: "April",
    5: "May",
    6: "June",
    7: "July",
    8: "August",
    9: "September",
    10: "October",
    11: "November",
    12: "December",
}

_WEEK_ORDINALS = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 5: "5th", -1: "last"}

# Safety bound on month-stepping searches (next/previous monthly occurrence) —
# comfortably more than a year either direction.
_MAX_MONTH_STEPS = 14


def _weekday_index(name) -> int | None:
    if not name:
        return None
    return WEEKDAY_NAMES.get(str(name).strip().lower())


def _add_month(year: int, month: int, step: int) -> tuple[int, int]:
    total = (year * 12 + (month - 1)) + step
    return total // 12, total % 12 + 1


def _nth_weekday_of_month(year: int, month: int, weekday: int, week: int) -> date | None:
    """The date of the ``week``-th ``weekday`` in ``year``/``month``
    (``week=-1`` means the last such weekday that month). None if that
    month doesn't have a ``week``-th occurrence (e.g. a 5th Friday)."""
    first = date(year, month, 1)
    first_weekday_offset = (weekday - first.weekday()) % 7
    first_match_day = 1 + first_weekday_offset

    if week == -1:
        day = first_match_day
        while True:
            candidate = day + 7
            try:
                date(year, month, candidate)
            except ValueError:
                break
            day = candidate
    else:
        day = first_match_day + 7 * (week - 1)

    try:
        return date(year, month, day)
    except ValueError:
        return None


def _next_annual_month_day(today: date, month: int, day: int) -> date | None:
    try:
        occ = date(today.year, month, day)
    except ValueError:
        return None
    if occ < today:
        try:
            occ = date(today.year + 1, month, day)
        except ValueError:
            return None
    return occ


def _previous_annual_month_day(today: date, month: int, day: int) -> date | None:
    try:
        occ = date(today.year, month, day)
    except ValueError:
        return None
    if occ > today:
        try:
            occ = date(today.year - 1, month, day)
        except ValueError:
            return None
    return occ


def _annual_window_dates(cadence: dict, today: date, *, forward: bool) -> date | None:
    """The next (or, ``forward=False``, previous) date among the annual
    ``apply_opens``/``apply_closes`` MM-DD fields — whichever is soonest."""
    candidates = []
    for key in ("apply_opens", "apply_closes"):
        raw = cadence.get(key)
        if not raw:
            continue
        try:
            month, day = (int(p) for p in str(raw).split("-"))
        except (ValueError, TypeError):
            continue
        occ = (
            _next_annual_month_day(today, month, day)
            if forward
            else _previous_annual_month_day(today, month, day)
        )
        if occ is not None:
            candidates.append(occ)
    if not candidates:
        return None
    return min(candidates) if forward else max(candidates)


def next_occurrence(cadence: dict | None, today: date | None = None) -> date | None:
    """The next occurrence on or after ``today``, or None when the cadence
    doesn't carry enough information to compute one (unconfirmed weekday,
    no anchor month, etc.)."""
    today = today or date.today()
    if not cadence:
        return None
    freq = str(cadence.get("freq") or "").lower()

    if freq in ("weekly", "biweekly"):
        weekday = _weekday_index(cadence.get("weekday"))
        if weekday is None:
            return None
        delta = (weekday - today.weekday()) % 7
        return today + timedelta(days=delta)

    if freq == "monthly":
        weekday = _weekday_index(cadence.get("weekday"))
        week = cadence.get("week")
        if weekday is None or week is None:
            return None
        year, month = today.year, today.month
        for _ in range(_MAX_MONTH_STEPS):
            occ = _nth_weekday_of_month(year, month, weekday, int(week))
            if occ is not None and occ >= today:
                return occ
            year, month = _add_month(year, month, 1)
        return None

    if freq == "annual":
        month = cadence.get("month")
        if month:
            return _next_annual_month_day(today, int(month), int(cadence.get("day") or 1))
        return _annual_window_dates(cadence, today, forward=True)

    return None


def previous_occurrence(cadence: dict | None, today: date | None = None) -> date | None:
    """The most recent occurrence on or before ``today`` — used to detect
    "this already happened" for the post-event recap prompt. Annual
    application windows have no meaningful "previous attendance", so they
    always return None here (recap only makes sense for events you go to)."""
    today = today or date.today()
    if not cadence:
        return None
    freq = str(cadence.get("freq") or "").lower()

    if freq in ("weekly", "biweekly"):
        weekday = _weekday_index(cadence.get("weekday"))
        if weekday is None:
            return None
        delta = (today.weekday() - weekday) % 7
        return today - timedelta(days=delta)

    if freq == "monthly":
        weekday = _weekday_index(cadence.get("weekday"))
        week = cadence.get("week")
        if weekday is None or week is None:
            return None
        year, month = today.year, today.month
        for _ in range(_MAX_MONTH_STEPS):
            occ = _nth_weekday_of_month(year, month, weekday, int(week))
            if occ is not None and occ <= today:
                return occ
            year, month = _add_month(year, month, -1)
        return None

    if freq == "annual":
        month = cadence.get("month")
        if month:
            return _previous_annual_month_day(today, int(month), int(cadence.get("day") or 1))
        return None

    return None


def describe_cadence(cadence: dict | None) -> str:
    """Human-readable summary for the scene calendar page."""
    if not cadence:
        return "no cadence set"
    freq = str(cadence.get("freq") or "").lower()
    weekday = cadence.get("weekday")
    weekday_label = str(weekday).capitalize() if weekday else "confirm night"

    if freq == "weekly":
        return f"Weekly — {weekday_label}"
    if freq == "biweekly":
        return f"Every 2 weeks — {weekday_label}"
    if freq == "monthly":
        week = cadence.get("week")
        if weekday and week in _WEEK_ORDINALS:
            return f"Monthly — {_WEEK_ORDINALS[week]} {str(weekday).capitalize()}"
        return "Monthly — confirm date"
    if freq == "bimonthly":
        return "Every 2 months — confirm date"
    if freq == "annual":
        month = cadence.get("month")
        if month:
            return f"Annual — {_MONTH_NAMES.get(int(month), month)}"
        opens, closes = cadence.get("apply_opens"), cadence.get("apply_closes")
        if opens or closes:
            return f"Annual — apply {opens or '?'} to {closes or '?'}"
        return "Annual — date not confirmed"
    return freq.capitalize() if freq else "no cadence set"
