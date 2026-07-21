from __future__ import annotations

from pathlib import Path

from vamp import db as vamp_db
from vamp import dedupe


def test_canonical_url_strips_tracking_params_and_www():
    a = dedupe.canonical_url(
        "https://www.Facebook.com/groups/okc/posts/123?utm_source=share&fbclid=abc"
    )
    b = dedupe.canonical_url("http://facebook.com/groups/okc/posts/123/")
    assert a == b


def test_canonical_url_none_for_garbage():
    assert dedupe.canonical_url("") is None
    assert dedupe.canonical_url("not a url") is None


def test_url_hash_stable_across_equivalent_urls():
    h1 = dedupe.url_hash("https://vastokc.example/jobs/pianist?utm_campaign=fb")
    h2 = dedupe.url_hash("https://www.vastokc.example/jobs/pianist")
    assert h1 == h2


def test_fuzzy_key_ignores_case_and_punctuation():
    k1 = dedupe.fuzzy_key("Solo Piano — Friday Brunch!", "Vast", "2026-09-12")
    k2 = dedupe.fuzzy_key("solo piano friday brunch", "vast", "2026-09-12")
    assert k1 == k2


def test_fuzzy_key_differs_for_different_leads():
    k1 = dedupe.fuzzy_key("Solo Piano", "Vast", "2026-09-12")
    k2 = dedupe.fuzzy_key("Duo Piano and Vocals", "Vast", "2026-09-12")
    assert k1 != k2


def test_find_duplicate_matches_on_either_key(tmp_path: Path):
    conn = vamp_db.get_connection(tmp_path / "vamp.db")
    try:
        conn.execute(
            "INSERT INTO leads (kind, dedupe_hash, url_hash, title) VALUES (?, ?, ?, ?)",
            ("gig", "fuzzy-abc", "url-xyz", "Solo piano"),
        )
        conn.commit()

        assert dedupe.find_duplicate(conn, "url-xyz", "different-fuzzy") is not None
        assert dedupe.find_duplicate(conn, "different-url", "fuzzy-abc") is not None
        assert dedupe.find_duplicate(conn, "no-match", "no-match") is None
    finally:
        conn.close()
