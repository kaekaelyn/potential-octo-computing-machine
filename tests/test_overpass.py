from __future__ import annotations

from pathlib import Path

from vamp import db as vamp_db
from vamp.config import load_config
from vamp.prospects.overpass import (
    CATEGORY_QUERIES,
    OKC_METRO_BBOX,
    OverpassImporter,
    build_query,
    parse_elements,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _conn(vamp_home: Path):
    return vamp_db.get_connection(load_config(home=vamp_home).db_path)


def test_build_query_covers_node_way_relation_and_bbox():
    query = build_query("coffee shop")
    assert '["amenity"="cafe"]' in query
    for element in ("node", "way", "relation"):
        assert f"{element}[" in query
    south, west, north, east = OKC_METRO_BBOX
    assert f"({south},{west},{north},{east})" in query
    assert "out center tags;" in query


def test_every_category_builds():
    for category in CATEGORY_QUERIES:
        assert build_query(category)


def test_parse_elements_drops_unnamed_and_maps_fields():
    payload = (FIXTURES / "overpass_coffee.json").read_text()
    records = parse_elements(payload, "coffee shop")
    # The third element has no name and must be dropped.
    assert len(records) == 2
    first = records[0]
    assert first.name == "Elemental Coffee Roasters"
    assert first.category == "coffee shop"
    assert first.area == "Oklahoma City"
    assert first.address == "815 N Hudson Ave, Oklahoma City, OK 73102"
    assert first.phone == "+1-405-555-0100"
    assert first.website == "https://example-elemental.test/"
    # contact:website should be picked up as website on the second record.
    assert records[1].website == "https://example-timber.test/"


def test_importer_inserts_as_unverified(vamp_home: Path):
    conn = _conn(vamp_home)
    try:
        payload = (FIXTURES / "overpass_coffee.json").read_text()
        importer = OverpassImporter(conn, fetch=lambda _query: payload)
        result = importer.import_category("coffee shop")
        assert result["ok"] is True
        assert result["imported"] == 2
        rows = conn.execute(
            "SELECT name, verified, source, socials_json FROM prospects "
            "WHERE source = 'overpass:coffee shop' ORDER BY name"
        ).fetchall()
        assert len(rows) == 2
        assert all(r["verified"] == 0 for r in rows)  # imports are always unverified
        assert "osm_id" in rows[0]["socials_json"]
    finally:
        conn.close()


def test_importer_is_idempotent_by_name_and_category(vamp_home: Path):
    conn = _conn(vamp_home)
    try:
        payload = (FIXTURES / "overpass_coffee.json").read_text()
        importer = OverpassImporter(conn, fetch=lambda _q: payload)
        importer.import_category("coffee shop")
        second = importer.import_category("coffee shop")
        assert second["imported"] == 0  # already present, not duplicated
        n = conn.execute(
            "SELECT COUNT(*) AS n FROM prospects WHERE source = 'overpass:coffee shop'"
        ).fetchone()["n"]
        assert n == 2
    finally:
        conn.close()


def test_importer_never_raises_on_bad_response(vamp_home: Path):
    conn = _conn(vamp_home)
    try:

        def boom(_query: str) -> str:
            raise RuntimeError("overpass 429 rate limited")

        importer = OverpassImporter(conn, fetch=boom)
        result = importer.import_category("coffee shop")
        assert result["ok"] is False
        assert "429" in result["error"]
        assert result["imported"] == 0
    finally:
        conn.close()
