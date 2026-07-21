"""Kit builder: an ordered, guided checklist for building the vault from
scratch (PLAN.md §5) — questionnaire → bios → shot list/headshots → three
live videos → repertoire list → CV → tech rider → rate card → EPK export.

Seeded once (idempotent, same pattern as ``sources.runner.
ensure_default_sources``); each task links to the asset kind it produces
so the checklist page can show "1 ready asset already in the vault"
alongside the manual todo/done toggle.
"""

from __future__ import annotations

import sqlite3

DEFAULT_KIT_TASKS: tuple[dict, ...] = (
    {
        "ord": 1,
        "title": "Write your bios",
        "detail": "Draft 50/150/300-word versions in your voice — most postings and "
        "programs want one of these three lengths.",
        "asset_kind": "bio",
    },
    {
        "ord": 2,
        "title": "Shot list + headshots",
        "detail": "A minimal shot list (one candid, one formal, one at the keys) and "
        "a friend with a decent phone camera is enough.",
        "asset_kind": "headshot",
    },
    {
        "ord": 3,
        "title": "Live video: solo piano improv",
        "detail": "One phone, one good take — a few minutes of free improvisation.",
        "asset_kind": "live_video",
    },
    {
        "ord": 4,
        "title": "Live video: voice + piano original",
        "detail": "One phone, one good take — an original song, voice and piano.",
        "asset_kind": "live_video",
    },
    {
        "ord": 5,
        "title": "Live video: covers sampler",
        "detail": "One phone, one good take — a short medley proving range and reading skill.",
        "asset_kind": "live_video",
    },
    {
        "ord": 6,
        "title": "Build the repertoire list",
        "detail": "Use the repertoire list builder to tag songs by occasion (wedding, "
        "cocktail, worship, jazz, originals, improv).",
        "asset_kind": "repertoire_list",
    },
    {
        "ord": 7,
        "title": "CV / resume",
        "detail": "Performance history, positions held, training — one page.",
        "asset_kind": "cv",
    },
    {
        "ord": 8,
        "title": "Tech rider + stage plot",
        "detail": "Your keyboard rig's power, DI, and space needs — reusable for every venue.",
        "asset_kind": "tech_rider",
    },
    {
        "ord": 9,
        "title": "Rate card",
        "detail": "Researched OKC-market rate ranges by gig type, plus your floor.",
        "asset_kind": "rate_card",
    },
    {
        "ord": 10,
        "title": "Export the EPK",
        "detail": "Once the vault has a bio, headshot, and at least one live video, "
        "export the self-contained EPK HTML file.",
        "asset_kind": "epk",
    },
)


def ensure_default_kit_tasks(conn: sqlite3.Connection) -> None:
    existing_titles = {row["title"] for row in conn.execute("SELECT title FROM kit_tasks")}
    for task in DEFAULT_KIT_TASKS:
        if task["title"] in existing_titles:
            continue
        conn.execute(
            "INSERT INTO kit_tasks (ord, title, detail, asset_kind, state) "
            "VALUES (?, ?, ?, ?, 'todo')",
            (task["ord"], task["title"], task["detail"], task["asset_kind"]),
        )
    conn.commit()


def list_kit_tasks(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM kit_tasks ORDER BY ord").fetchall()


def set_kit_task_state(conn: sqlite3.Connection, task_id: int, state: str) -> None:
    conn.execute("UPDATE kit_tasks SET state = ? WHERE id = ?", (state, task_id))
    conn.commit()
