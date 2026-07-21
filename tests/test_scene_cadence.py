from __future__ import annotations

from datetime import date

from vamp.scene import cadence


def test_weekly_next_and_previous_occurrence():
    c = {"freq": "weekly", "weekday": "friday"}
    today = date(2026, 7, 21)  # a Tuesday
    assert cadence.next_occurrence(c, today) == date(2026, 7, 24)
    assert cadence.previous_occurrence(c, today) == date(2026, 7, 17)


def test_weekly_on_the_exact_weekday_returns_today():
    c = {"freq": "weekly", "weekday": "tuesday"}
    today = date(2026, 7, 21)  # itself a Tuesday
    assert cadence.next_occurrence(c, today) == today
    assert cadence.previous_occurrence(c, today) == today


def test_weekly_with_unconfirmed_weekday_is_unknown():
    c = {"freq": "weekly", "weekday": None}
    assert cadence.next_occurrence(c, date(2026, 7, 21)) is None
    assert cadence.previous_occurrence(c, date(2026, 7, 21)) is None


def test_monthly_first_friday_next_and_previous():
    # PLAN.md's seeded First Friday Gallery Walk cadence shape.
    c = {"freq": "monthly", "week": 1, "weekday": "friday"}
    today = date(2026, 7, 21)  # after July's 1st Friday (July 3)
    assert cadence.next_occurrence(c, today) == date(2026, 8, 7)
    assert cadence.previous_occurrence(c, today) == date(2026, 7, 3)


def test_monthly_last_weekday():
    c = {"freq": "monthly", "week": -1, "weekday": "friday"}
    # July 2026's last Friday is the 31st.
    assert cadence.next_occurrence(c, date(2026, 7, 1)) == date(2026, 7, 31)


def test_monthly_missing_week_or_weekday_is_unknown():
    assert (
        cadence.next_occurrence({"freq": "monthly", "weekday": "friday"}, date(2026, 7, 21)) is None
    )
    assert cadence.next_occurrence({"freq": "monthly", "week": 1}, date(2026, 7, 21)) is None


def test_annual_month_day_wraps_to_next_year_once_passed():
    c = {"freq": "annual", "month": 4, "day": 1}
    today = date(2026, 7, 21)
    assert cadence.next_occurrence(c, today) == date(2027, 4, 1)
    assert cadence.previous_occurrence(c, today) == date(2026, 4, 1)


def test_annual_month_defaults_day_to_first():
    c = {"freq": "annual", "month": 12}
    assert cadence.next_occurrence(c, date(2026, 7, 21)) == date(2026, 12, 1)


def test_annual_apply_window_picks_the_soonest_future_date():
    # Kerrville New Folk Competition's seeded shape: opens Jan 2, closes Mar 2.
    c = {"freq": "annual", "apply_opens": "01-02", "apply_closes": "03-02"}
    # Before the window opens: soonest is the open date.
    assert cadence.next_occurrence(c, date(2025, 12, 1)) == date(2026, 1, 2)
    # After it opens but before it closes: soonest is the close (deadline).
    assert cadence.next_occurrence(c, date(2026, 1, 15)) == date(2026, 3, 2)
    # After both have passed this year: rolls to next year's open date.
    assert cadence.next_occurrence(c, date(2026, 6, 1)) == date(2027, 1, 2)


def test_annual_apply_window_has_no_previous_occurrence_for_recap():
    # Application windows aren't "attendance" events — no recap prompt makes
    # sense for them, so previous_occurrence stays None.
    c = {"freq": "annual", "apply_opens": "01-02", "apply_closes": "03-02"}
    assert cadence.previous_occurrence(c, date(2026, 7, 21)) is None


def test_bimonthly_with_no_anchor_is_unknown():
    # No anchor month/day is given anywhere in the seeded data for
    # bimonthly cadences — never fabricate one.
    assert cadence.next_occurrence({"freq": "bimonthly"}, date(2026, 7, 21)) is None
    assert cadence.previous_occurrence({"freq": "bimonthly"}, date(2026, 7, 21)) is None


def test_empty_or_missing_cadence_is_unknown():
    assert cadence.next_occurrence(None, date(2026, 7, 21)) is None
    assert cadence.next_occurrence({}, date(2026, 7, 21)) is None


def test_describe_cadence_shapes():
    assert cadence.describe_cadence({"freq": "monthly", "week": 1, "weekday": "friday"}) == (
        "Monthly — 1st Friday"
    )
    assert cadence.describe_cadence({"freq": "weekly", "weekday": None}) == "Weekly — confirm night"
    assert cadence.describe_cadence({"freq": "annual", "month": 4}) == "Annual — April"
    assert (
        cadence.describe_cadence(
            {"freq": "annual", "apply_opens": "01-02", "apply_closes": "03-02"}
        )
        == "Annual — apply 01-02 to 03-02"
    )
    assert cadence.describe_cadence(None) == "no cadence set"
