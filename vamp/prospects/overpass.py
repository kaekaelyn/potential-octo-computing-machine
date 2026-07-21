"""OpenStreetMap Overpass API importer (PLAN.md §3/§6): free, legit bulk
discovery of category × geography as raw prospect material.

Everything imported here is ``verified: false`` by construction — OSM is
crowd-sourced, so a place, its phone number, or its website may be stale or
wrong. The import fills only fields OSM actually carries; it never invents a
contact detail (CLAUDE.md hard rule). Rows land with a "confirm before
pitching" flag and are meant to be verified by hand before any outreach.

Network access is injectable (``fetch``) so tests run against a recorded
fixture and never hit the live API (CLAUDE.md: tests never perform live HTTP).
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

# OKC metro bounding box (south, west, north, east). Covers Oklahoma City and
# the ring the plan cares about — Edmond, Norman, Moore, Yukon, Mustang,
# Bethany, Midwest City, Del City (PLAN.md §4 distance decay ~45 min).
OKC_METRO_BBOX: tuple[float, float, float, float] = (35.10, -97.90, 35.55, -97.10)

OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter"
FETCH_TIMEOUT_SECONDS = 90.0
USER_AGENT = "Vamp/0.1 (local single-user musician-work copilot; OSM Overpass import)"

# Category → OSM tag filters. Each tuple is one ["key"="value"] selector; a
# category unions several. Chosen to map onto the prospect categories in the
# seed data so imported raw rows slot beside the curated ones.
CATEGORY_QUERIES: dict[str, tuple[tuple[str, str], ...]] = {
    "restaurant": (("amenity", "restaurant"),),
    "bar": (("amenity", "bar"), ("amenity", "pub")),
    "coffee shop": (("amenity", "cafe"),),
    "hotel": (("tourism", "hotel"),),
    "brewery": (("craft", "brewery"), ("microbrewery", "yes")),
    "winery": (("craft", "winery"), ("shop", "wine")),
    "retirement community": (
        ("amenity", "social_facility"),
        ("social_facility", "assisted_living"),
        ("social_facility", "nursing_home"),
    ),
    "funeral home": (("shop", "funeral_directors"), ("amenity", "funeral_hall")),
    "museum": (("tourism", "museum"),),
    "gallery": (("tourism", "gallery"), ("shop", "art")),
    "theater": (("amenity", "theatre"),),
    "church": (("amenity", "place_of_worship"),),
    "country club": (("leisure", "golf_course"),),
    "dance studio": (("leisure", "dance"), ("amenity", "dancing_school")),
    "yoga studio": (("sport", "yoga"),),
}

Fetcher = Callable[[str], str]


def _default_fetch(query: str) -> str:
    response = httpx.post(
        OVERPASS_ENDPOINT,
        data={"data": query},
        timeout=FETCH_TIMEOUT_SECONDS,
        headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    return response.text


def build_query(category: str, bbox: tuple[float, float, float, float] = OKC_METRO_BBOX) -> str:
    """Overpass QL for one category over the bbox: nodes, ways, and relations
    for each tag selector, returned with centers so ways/relations have a
    coordinate."""
    if category not in CATEGORY_QUERIES:
        raise ValueError(f"unknown Overpass category: {category!r}")
    south, west, north, east = bbox
    bbox_str = f"({south},{west},{north},{east})"
    parts = []
    for key, value in CATEGORY_QUERIES[category]:
        selector = f'["{key}"="{value}"]'
        for element in ("node", "way", "relation"):
            parts.append(f"  {element}{selector}{bbox_str};")
    body = "\n".join(parts)
    return f"[out:json][timeout:90];\n(\n{body}\n);\nout center tags;"


@dataclass
class OverpassProspect:
    name: str
    category: str
    area: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    socials_json: str | None = None
    raw_tags: dict = field(default_factory=dict)


def _first(tags: dict, *keys: str) -> str | None:
    for key in keys:
        value = tags.get(key)
        if value:
            return value.strip()
    return None


def _compose_address(tags: dict) -> str | None:
    house = tags.get("addr:housenumber")
    street = tags.get("addr:street")
    parts = []
    if house and street:
        parts.append(f"{house} {street}")
    elif street:
        parts.append(street)
    city = tags.get("addr:city")
    if city:
        parts.append(city)
    state = tags.get("addr:state")
    postcode = tags.get("addr:postcode")
    tail = " ".join(p for p in (state, postcode) if p)
    if tail:
        parts.append(tail)
    return ", ".join(parts) if parts else None


def parse_elements(payload: str, category: str) -> list[OverpassProspect]:
    """Turn an Overpass JSON response into prospect records, dropping unnamed
    elements (a place with no name isn't a pitchable prospect)."""
    data = json.loads(payload)
    out: list[OverpassProspect] = []
    for element in data.get("elements", []):
        tags = element.get("tags") or {}
        name = _first(tags, "name")
        if not name:
            continue
        osm_ref = {"osm_type": element.get("type"), "osm_id": element.get("id")}
        out.append(
            OverpassProspect(
                name=name,
                category=category,
                area=tags.get("addr:city"),
                address=_compose_address(tags),
                phone=_first(tags, "phone", "contact:phone"),
                email=_first(tags, "email", "contact:email"),
                website=_first(tags, "website", "contact:website"),
                socials_json=json.dumps(osm_ref),
                raw_tags=tags,
            )
        )
    return out


class OverpassImporter:
    def __init__(
        self,
        conn: sqlite3.Connection,
        fetch: Fetcher | None = None,
        bbox: tuple[float, float, float, float] = OKC_METRO_BBOX,
    ):
        self.conn = conn
        self.bbox = bbox
        self._fetch = fetch or _default_fetch

    def _exists(self, name: str, category: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM prospects WHERE lower(name) = lower(?) AND category = ? LIMIT 1",
            (name, category),
        ).fetchone()
        return row is not None

    def import_category(self, category: str) -> dict:
        """Fetch + import one category. Never raises on a bad response — like
        the M2 source runner, one category's failure must not sink the rest."""
        try:
            query = build_query(category, self.bbox)
            payload = self._fetch(query)
            records = parse_elements(payload, category)
        except Exception as exc:  # noqa: BLE001 - isolate one category's failure
            return {"category": category, "ok": False, "error": str(exc), "imported": 0, "seen": 0}

        imported = 0
        for rec in records:
            if self._exists(rec.name, rec.category):
                continue
            self.conn.execute(
                """
                INSERT INTO prospects (
                    name, category, area, address, phone, email, website,
                    socials_json, has_piano, angle, status, source, verified, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, 'identified',
                          ?, 0, ?)
                """,
                (
                    rec.name,
                    rec.category,
                    rec.area,
                    rec.address,
                    rec.phone,
                    rec.email,
                    rec.website,
                    rec.socials_json,
                    f"overpass:{category}",
                    "Imported from OpenStreetMap — confirm details before pitching.",
                ),
            )
            imported += 1
        self.conn.execute(
            "INSERT INTO events (kind, payload_json) VALUES ('overpass_import', ?)",
            (json.dumps({"category": category, "seen": len(records), "imported": imported}),),
        )
        self.conn.commit()
        return {
            "category": category,
            "ok": True,
            "error": None,
            "imported": imported,
            "seen": len(records),
        }

    def import_categories(self, categories: list[str]) -> list[dict]:
        return [self.import_category(c) for c in categories]
