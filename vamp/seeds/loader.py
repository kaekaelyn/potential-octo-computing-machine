"""Idempotent YAML seed loader (PLAN.md §6/§12 M4, CLAUDE.md tech conventions).

Runs in the DB-setup flow (called from the app factory right after migrations,
same shape as ``ensure_default_sources``/``ensure_default_kit_tasks``) and from
``vamp seed``. Curated rows (prospects, scene events, patrol items, rate
ranges) are inserted only when absent — a human may have edited, advanced, or
marked a seeded row dead, and re-import must never clobber that. Playbooks are
editorial content with no user-owned state, so they're refreshed from the repo
on each load by their stable ``slug``.

Everything about verification lives in the YAML itself: each row carries a
``verified`` flag, and any contact field the research couldn't confirm is left
empty rather than invented (CLAUDE.md hard rule: never fabricate a contact).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import yaml

from vamp.db import REPO_ROOT

SEEDS_DIR = REPO_ROOT / "seeds"
PLAYBOOKS_DIR = SEEDS_DIR / "playbooks"


def _load_yaml(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text()) or []
    if not isinstance(data, list):
        raise ValueError(f"{path.name}: expected a top-level list, got {type(data).__name__}")
    return data


def _as_flag(value, default: int = 0) -> int:
    if value is None:
        return default
    return 1 if bool(value) else 0


def _tri_flag(value):
    """has_piano is tri-state: True/False/unknown(NULL)."""
    if value is None:
        return None
    return 1 if bool(value) else 0


def _socials(row: dict) -> str | None:
    socials = row.get("socials")
    if socials is None:
        return row.get("socials_json")
    return json.dumps(socials)


def load_prospects(conn: sqlite3.Connection, rows: list[dict]) -> int:
    inserted = 0
    for row in rows:
        name = (row.get("name") or "").strip()
        category = (row.get("category") or "").strip()
        if not name or not category:
            continue
        exists = conn.execute(
            "SELECT 1 FROM prospects WHERE lower(name) = lower(?) AND category = ? LIMIT 1",
            (name, category),
        ).fetchone()
        if exists:
            continue
        conn.execute(
            """
            INSERT INTO prospects (
                name, category, area, address, phone, email, website, socials_json,
                has_piano, angle, status, source, verified, notes, cooldown_days, playbook
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                category,
                row.get("area"),
                row.get("address"),
                row.get("phone"),
                row.get("email"),
                row.get("website"),
                _socials(row),
                _tri_flag(row.get("has_piano")),
                row.get("angle"),
                row.get("status") or "identified",
                row.get("source") or "seed",
                _as_flag(row.get("verified")),
                row.get("notes"),
                row.get("cooldown_days"),
                row.get("playbook"),
            ),
        )
        inserted += 1
    conn.commit()
    return inserted


def load_scene_events(conn: sqlite3.Connection, rows: list[dict]) -> int:
    inserted = 0
    for row in rows:
        name = (row.get("name") or "").strip()
        if not name:
            continue
        exists = conn.execute(
            "SELECT 1 FROM scene_events WHERE lower(name) = lower(?) LIMIT 1", (name,)
        ).fetchone()
        if exists:
            continue
        cadence = row.get("cadence")
        cadence_json = json.dumps(cadence) if cadence is not None else row.get("cadence_json")
        conn.execute(
            """
            INSERT INTO scene_events
                (name, cadence_json, venue, area, url, kind, notes, going, playbook)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
            """,
            (
                name,
                cadence_json,
                row.get("venue"),
                row.get("area"),
                row.get("url"),
                row.get("kind"),
                row.get("notes"),
                row.get("playbook"),
            ),
        )
        inserted += 1
    conn.commit()
    return inserted


def load_patrol_items(conn: sqlite3.Connection, rows: list[dict]) -> int:
    inserted = 0
    for row in rows:
        name = (row.get("name") or "").strip()
        if not name:
            continue
        exists = conn.execute(
            "SELECT 1 FROM patrol_items WHERE lower(name) = lower(?) LIMIT 1", (name,)
        ).fetchone()
        if exists:
            continue
        conn.execute(
            "INSERT INTO patrol_items (name, url, notes) VALUES (?, ?, ?)",
            (name, row.get("url"), row.get("notes")),
        )
        inserted += 1
    conn.commit()
    return inserted


def load_rate_ranges(conn: sqlite3.Connection, rows: list[dict]) -> int:
    inserted = 0
    for row in rows:
        gig_type = (row.get("gig_type") or "").strip()
        if not gig_type:
            continue
        area = row.get("area") or "OKC metro"
        exists = conn.execute(
            "SELECT 1 FROM rate_ranges WHERE lower(gig_type) = lower(?) AND area = ? LIMIT 1",
            (gig_type, area),
        ).fetchone()
        if exists:
            continue
        conn.execute(
            """
            INSERT INTO rate_ranges (gig_type, low, high, unit, area, notes, source, verified)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                gig_type,
                row.get("low"),
                row.get("high"),
                row.get("unit"),
                area,
                row.get("notes"),
                row.get("source"),
                _as_flag(row.get("verified")),
            ),
        )
        inserted += 1
    conn.commit()
    return inserted


def load_playbooks(
    conn: sqlite3.Connection, rows: list[dict], playbooks_dir: Path = PLAYBOOKS_DIR
) -> int:
    """Playbooks are content: upsert by slug so edits in the repo flow through
    on the next load (there is no user-owned state on a playbook row)."""
    loaded = 0
    for row in rows:
        slug = (row.get("slug") or "").strip()
        title = (row.get("title") or "").strip()
        if not slug or not title:
            continue
        body_file = row.get("body_file")
        if body_file:
            body_md = (playbooks_dir / body_file).read_text()
        else:
            body_md = row.get("body_md") or ""
        active = row.get("active_months")
        active_months = ",".join(str(m) for m in active) if isinstance(active, list) else active
        conn.execute(
            """
            INSERT INTO playbooks (slug, title, body_md, active_months)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(slug) DO UPDATE SET
                title = excluded.title,
                body_md = excluded.body_md,
                active_months = excluded.active_months
            """,
            (slug, title, body_md, active_months),
        )
        loaded += 1
    conn.commit()
    return loaded


def ensure_seed_data(conn: sqlite3.Connection, seeds_dir: Path = SEEDS_DIR) -> dict:
    """Idempotently import every seed dataset. Safe to call on every startup."""
    return {
        "prospects": load_prospects(conn, _load_yaml(seeds_dir / "prospects.yaml")),
        "scene_events": load_scene_events(conn, _load_yaml(seeds_dir / "scene_events.yaml")),
        "patrol_items": load_patrol_items(conn, _load_yaml(seeds_dir / "patrol.yaml")),
        "rate_ranges": load_rate_ranges(conn, _load_yaml(seeds_dir / "rate_ranges.yaml")),
        "playbooks": load_playbooks(
            conn, _load_yaml(seeds_dir / "playbooks.yaml"), seeds_dir / "playbooks"
        ),
    }
