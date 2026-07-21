"""Bio drafting for the kit builder (PLAN.md §5/§9 priority #4): 50/150/
300-word versions in her voice, drafted from her profile fields — a
starting point to edit and save into the vault as a ``bio`` asset, not a
finished, unread artifact."""

from __future__ import annotations

import sqlite3

from vamp.ai import drafts as drafts_service
from vamp.ai.provider import Provider
from vamp.ai.router import run
from vamp.profile import service as profile_service

DRAFT_KIND = "bio"

SYSTEM_PROMPT = (
    "You draft an artist bio for a working musician (pianist/vocalist/free "
    "improviser). Write three versions at three lengths. Match the writer's "
    "own voice sample if one is given; otherwise use a warm, plainspoken, "
    "unpretentious tone. Never invent credits, venues, or credentials not "
    "given to you."
)

SCHEMA_FIELDS = {
    "bio_50": "a roughly 50-word bio",
    "bio_150": "a roughly 150-word bio",
    "bio_300": "a roughly 300-word bio",
}


def build_prompt(conn: sqlite3.Connection) -> tuple[str, str, dict]:
    profile = profile_service.get_profile(conn)
    prompt = (
        f"Name: {profile['display_name']}\n"
        f"Instrument(s)/role: {profile['instrument']}\n"
        f"Home area: {profile['home_area']}\n"
        f"Voice sample (match this tone/style if present):\n"
        f"{profile['voice_sample'] or 'none on file'}"
    )
    schema = {"task": "draft_bio", "fields": SCHEMA_FIELDS, "context": profile}
    return SYSTEM_PROMPT, prompt, schema


def _normalize(result: dict) -> dict:
    return {
        "bio_50": str(result.get("bio_50") or ""),
        "bio_150": str(result.get("bio_150") or ""),
        "bio_300": str(result.get("bio_300") or ""),
    }


def draft_bio(conn: sqlite3.Connection, provider: Provider) -> dict:
    system, prompt, schema = build_prompt(conn)
    raw_result, used_provider = run(provider, system, prompt, schema)
    result = _normalize(raw_result)
    drafts_service.save_draft(
        conn,
        kind=DRAFT_KIND,
        ref_kind="profile",
        ref_id=None,
        provider=used_provider,
        content=result,
    )
    return {**result, "provider": used_provider}


def latest_bio(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return drafts_service.latest_draft(conn, kind=DRAFT_KIND, ref_kind="profile", ref_id=None)
