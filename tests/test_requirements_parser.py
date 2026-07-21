from __future__ import annotations

from pathlib import Path

import pytest

from vamp.requirements.parser import parse_requirements

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "requirements"

# fixture filename -> expected requirement kinds (order-independent)
EXPECTED_KINDS: dict[str, set[str]] = {
    "church_pianist_resume_references.txt": {"cv", "references"},
    "wedding_venue_video_repertoire.txt": {"live_video", "repertoire_list"},
    "jazz_club_audio_demo_bio.txt": {"audio_demo", "bio"},
    "hotel_lounge_epk.txt": {"epk_link"},
    "retirement_community_headshot_repertoire.txt": {"headshot", "repertoire_list"},
    "military_band_audition_cv.txt": {"in_person_audition", "cv"},
    "theater_accompanist_cover_letter_cv.txt": {"cv", "cover_letter"},
    "piano_bar_live_video.txt": {"live_video"},
    "worship_leader_bio_references.txt": {"bio", "references"},
    "wedding_planner_epk_website.txt": {"epk_link"},
    "restaurant_lounge_headshot_video.txt": {"live_video", "headshot"},
    "songwriter_showcase_audio_demo.txt": {"audio_demo", "bio"},
    "accompanist_audition_inperson.txt": {"in_person_audition"},
    "corporate_event_bio_video.txt": {"bio", "live_video"},
    "open_mic_no_requirements.txt": set(),
    "multi_requirement_full_kit.txt": {
        "cv",
        "bio",
        "references",
        "live_video",
        "in_person_audition",
    },
    "vague_other_requirement.txt": {"other"},
}


def test_fixture_corpus_has_at_least_fifteen_entries():
    assert len(EXPECTED_KINDS) >= 15


@pytest.mark.parametrize("filename", sorted(EXPECTED_KINDS))
def test_parses_expected_requirement_kinds(filename: str):
    text = (FIXTURES_DIR / filename).read_text()

    parsed = parse_requirements(text)

    assert {r.kind for r in parsed} == EXPECTED_KINDS[filename]


def test_every_fixture_file_is_covered_by_the_expectations_table():
    on_disk = {p.name for p in FIXTURES_DIR.glob("*.txt")}
    assert on_disk == set(EXPECTED_KINDS)


def test_empty_text_yields_no_requirements():
    assert parse_requirements("") == []
    assert parse_requirements(None) == []


def test_requirements_are_ordered_per_canonical_kind_order():
    text = (FIXTURES_DIR / "multi_requirement_full_kit.txt").read_text()

    parsed = parse_requirements(text)
    kinds = [r.kind for r in parsed]

    assert kinds == sorted(kinds, key=lambda k: kinds.index(k))  # stable
    # live_video comes before cv/bio/references/in_person_audition per
    # REQUIREMENT_KINDS canonical order.
    assert kinds.index("live_video") < kinds.index("cv")
    assert kinds.index("cv") < kinds.index("bio")
    assert kinds.index("references") < kinds.index("in_person_audition")
