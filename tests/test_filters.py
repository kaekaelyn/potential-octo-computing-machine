from __future__ import annotations

from pathlib import Path

from vamp.filters import run_hard_filters
from vamp.filters.degree import check_degree
from vamp.filters.pay_to_play import check_pay_to_play
from vamp.filters.teaching import check_teaching

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_teaching_posting_is_excluded():
    text = _fixture("posting_teaching.txt")
    assert check_teaching(text) == "teaching"
    assert "teaching" in run_hard_filters(text)


def test_degree_wall_without_carve_out_is_excluded():
    text = _fixture("posting_degree_wall.txt")
    assert check_degree(text) == "degree-wall"
    assert "degree-wall" in run_hard_filters(text)


def test_degree_with_or_equivalent_carve_out_is_not_excluded():
    text = _fixture("posting_degree_equivalent.txt")
    assert check_degree(text) is None
    assert run_hard_filters(text) == []


def test_pay_to_play_is_excluded():
    text = _fixture("posting_pay_to_play.txt")
    assert check_pay_to_play(text) == "pay-to-play"
    assert "pay-to-play" in run_hard_filters(text)


def test_clean_paid_posting_triggers_no_filters():
    assert run_hard_filters(_fixture("posting_clean_paid.txt")) == []


def test_clean_unpaid_posting_triggers_no_filters():
    # Unpaid on its own is not pay-to-play — no required ticket sales here.
    assert run_hard_filters(_fixture("posting_clean_unpaid.txt")) == []


def test_multiple_reasons_can_fire_together():
    text = (
        "Piano teacher wanted for private lessons. Performers must purchase "
        "a minimum of 10 tickets to be considered."
    )
    reasons = run_hard_filters(text)
    assert set(reasons) == {"teaching", "pay-to-play"}


def test_degree_mention_without_requirement_language_is_not_excluded():
    text = "A music degree is a plus but not necessary — we care about your playing."
    assert check_degree(text) is None
