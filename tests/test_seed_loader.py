"""Seed loader behavior + a data-integrity guard over the researched seed
datasets (PLAN.md §12 M4 acceptance: no fabrication, no dangling references)."""

from __future__ import annotations

from pathlib import Path

import yaml

from vamp import db as vamp_db
from vamp.config import load_config
from vamp.seeds import loader
from vamp.seeds.loader import SEEDS_DIR, ensure_seed_data


def _conn(vamp_home: Path):
    return vamp_db.get_connection(load_config(home=vamp_home).db_path)


def _load(name: str) -> list[dict]:
    return yaml.safe_load((SEEDS_DIR / name).read_text()) or []


def test_ensure_seed_data_is_idempotent(vamp_home: Path):
    conn = _conn(vamp_home)
    try:
        first = ensure_seed_data(conn)
        second = ensure_seed_data(conn)
        # Curated datasets insert-if-absent, so a second pass adds nothing.
        for key in ("prospects", "scene_events", "patrol_items", "rate_ranges"):
            assert first[key] > 0, f"expected {key} to seed on first load"
            assert second[key] == 0, f"{key} should not re-insert"
    finally:
        conn.close()


def test_playbooks_load_and_render_bodies(vamp_home: Path):
    conn = _conn(vamp_home)
    try:
        ensure_seed_data(conn)
        rows = conn.execute("SELECT slug, title, body_md FROM playbooks").fetchall()
        assert len(rows) == 7
        for row in rows:
            assert row["body_md"].strip(), f"{row['slug']} has an empty body"
    finally:
        conn.close()


def test_every_prospect_has_required_fields_and_valid_flags():
    prospects = _load("prospects.yaml")
    assert len(prospects) >= 40
    for p in prospects:
        assert p.get("name"), f"prospect missing name: {p}"
        assert p.get("category"), f"prospect missing category: {p['name']}"
        assert p.get("angle"), f"prospect missing angle: {p['name']}"
        assert isinstance(p.get("verified"), bool), f"verified must be bool: {p['name']}"
        website = p.get("website")
        if website:
            assert website.startswith("http"), f"bad website for {p['name']}: {website}"


def test_prospect_playbook_slugs_resolve():
    slugs = {pb["slug"] for pb in _load("playbooks.yaml")}
    for p in _load("prospects.yaml"):
        if p.get("playbook"):
            assert p["playbook"] in slugs, (
                f"{p['name']} references unknown playbook {p['playbook']}"
            )


def test_scene_event_playbook_slugs_resolve():
    slugs = {pb["slug"] for pb in _load("playbooks.yaml")}
    for e in _load("scene_events.yaml"):
        if e.get("playbook"):
            assert e["playbook"] in slugs, (
                f"{e['name']} references unknown playbook {e['playbook']}"
            )


def test_every_playbook_body_file_exists():
    for pb in _load("playbooks.yaml"):
        body_file = pb.get("body_file")
        assert body_file, f"playbook {pb['slug']} has no body_file"
        assert (loader.PLAYBOOKS_DIR / body_file).exists(), f"missing body: {body_file}"


def test_a_meaningful_share_of_prospects_is_verified():
    prospects = _load("prospects.yaml")
    verified = [p for p in prospects if p.get("verified")]
    # The research session confirmed a solid core; the rest are honestly flagged.
    assert len(verified) >= 20
