"""Per-prospect pitch drafting (PLAN.md §6/§9 priority #3): vault bio +
the prospect's angle + her voice sample from profile, drafted — never
sent. "Kaelyn sends every message herself; Vamp does everything up to
'press send.'" (PLAN.md §6)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from vamp.ai import drafts as drafts_service
from vamp.ai.provider import Provider
from vamp.ai.router import run
from vamp.profile import service as profile_service
from vamp.vault.assets import is_local_file

DRAFT_KIND = "pitch"

SYSTEM_PROMPT = (
    "You draft a short, warm, non-spammy cold-outreach pitch email from a "
    "working musician to a venue/organization that might book live piano. "
    "Match the writer's own voice sample if one is given. Keep it brief — "
    "three short paragraphs at most. Never invent facts about the venue "
    "beyond what's given."
)

SCHEMA_FIELDS = {
    "subject": "a short email subject line",
    "body": "the email body, plain text, no signature block beyond the writer's name",
}


def _bio_text(conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        "SELECT path_or_url FROM assets WHERE kind = 'bio' AND ready = 1 "
        "ORDER BY updated_at DESC, id DESC LIMIT 1"
    ).fetchone()
    if row is None or not row["path_or_url"]:
        return None
    if not is_local_file(row["path_or_url"]):
        return None
    path = Path(row["path_or_url"])
    if not path.exists() or path.suffix.lower() not in (".txt", ".md"):
        return None
    return path.read_text()


def build_prompt(conn: sqlite3.Connection, prospect: sqlite3.Row) -> tuple[str, str, dict]:
    profile = profile_service.get_profile(conn)
    bio = _bio_text(conn)
    ctx = {
        "prospect_name": prospect["name"],
        "category": prospect["category"],
        "area": prospect["area"],
        "angle": prospect["angle"],
        "display_name": profile["display_name"],
        "instrument": profile["instrument"],
        "voice_sample": profile["voice_sample"] or None,
        "bio": bio,
    }
    prompt = (
        f"Venue/organization: {ctx['prospect_name']} ({ctx['category'] or 'unknown category'}, "
        f"{ctx['area'] or 'OKC metro'})\n"
        f"Angle (why this pitch, specifically): {ctx['angle'] or 'no angle recorded yet'}\n"
        f"Writer: {ctx['display_name']}, {ctx['instrument']}\n"
        f"Writer's bio: {bio or 'none on file'}\n"
        f"Writer's voice sample (match this tone/style if present):\n"
        f"{ctx['voice_sample'] or 'none on file — use a warm, direct, unpretentious tone'}"
    )
    schema = {"task": "draft_pitch", "fields": SCHEMA_FIELDS, "context": ctx}
    return SYSTEM_PROMPT, prompt, schema


def _normalize(result: dict) -> dict:
    return {
        "subject": str(result.get("subject") or ""),
        "body": str(result.get("body") or ""),
    }


def draft_pitch(conn: sqlite3.Connection, provider: Provider, prospect: sqlite3.Row) -> dict:
    system, prompt, schema = build_prompt(conn, prospect)
    raw_result, used_provider = run(provider, system, prompt, schema)
    result = _normalize(raw_result)
    drafts_service.save_draft(
        conn,
        kind=DRAFT_KIND,
        ref_kind="prospect",
        ref_id=prospect["id"],
        provider=used_provider,
        content=result,
    )
    return {**result, "provider": used_provider}


def latest_pitch(conn: sqlite3.Connection, prospect_id: int) -> sqlite3.Row | None:
    return drafts_service.latest_draft(
        conn, kind=DRAFT_KIND, ref_kind="prospect", ref_id=prospect_id
    )
