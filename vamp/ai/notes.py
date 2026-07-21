"""Follow-up and sub-availability note drafting (PLAN.md §6/§9 priority
#5) — one-tap drafts for the cadence engine's follow-ups and the Sub List
playbook's "available this Sunday" notes (PLAN.md §6 playbook 4). Drafts
only; nothing here sends anything.
"""

from __future__ import annotations

import sqlite3

from vamp.ai import drafts as drafts_service
from vamp.ai.provider import Provider
from vamp.ai.router import run
from vamp.profile import service as profile_service

FOLLOWUP_KIND = "followup"
SUB_AVAILABILITY_KIND = "sub_availability"

_FOLLOWUP_SYSTEM = (
    "You draft a brief, low-pressure follow-up note from a musician to a "
    "venue/organization she pitched earlier and hasn't heard back from. "
    "Keep it short and friendly, not pushy."
)
_FOLLOWUP_FIELDS = {
    "subject": "a short email subject line",
    "body": "the follow-up note body, plain text",
}

_SUB_SYSTEM = (
    "You draft a short 'available to sub' note from a pianist to a church or "
    "band's music director, letting them know she's free on a given date."
)
_SUB_FIELDS = {
    "subject": "a short subject line",
    "body": "the note body, plain text",
}


def _normalize(result: dict) -> dict:
    return {"subject": str(result.get("subject") or ""), "body": str(result.get("body") or "")}


def build_followup_prompt(conn: sqlite3.Connection, prospect: sqlite3.Row) -> tuple[str, str, dict]:
    profile = profile_service.get_profile(conn)
    ctx = {
        "prospect_name": prospect["name"],
        "angle": prospect["angle"],
        "display_name": profile["display_name"],
    }
    prompt = (
        f"Venue/organization: {ctx['prospect_name']}\n"
        f"Original pitch angle: {ctx['angle'] or 'none recorded'}\n"
        f"Writer: {ctx['display_name']}"
    )
    schema = {"task": "draft_followup", "fields": _FOLLOWUP_FIELDS, "context": ctx}
    return _FOLLOWUP_SYSTEM, prompt, schema


def draft_followup(conn: sqlite3.Connection, provider: Provider, prospect: sqlite3.Row) -> dict:
    system, prompt, schema = build_followup_prompt(conn, prospect)
    raw_result, used_provider = run(provider, system, prompt, schema)
    result = _normalize(raw_result)
    drafts_service.save_draft(
        conn,
        kind=FOLLOWUP_KIND,
        ref_kind="prospect",
        ref_id=prospect["id"],
        provider=used_provider,
        content=result,
    )
    return {**result, "provider": used_provider}


def build_sub_availability_prompt(
    conn: sqlite3.Connection, prospect: sqlite3.Row | None, date: str
) -> tuple[str, str, dict]:
    profile = profile_service.get_profile(conn)
    ctx = {
        "prospect_name": prospect["name"] if prospect is not None else None,
        "date": date,
        "display_name": profile["display_name"],
    }
    prompt = (
        f"Recipient: {ctx['prospect_name'] or 'a church/band music director'}\n"
        f"Date available: {date}\n"
        f"Writer: {ctx['display_name']}"
    )
    schema = {"task": "draft_sub_availability", "fields": _SUB_FIELDS, "context": ctx}
    return _SUB_SYSTEM, prompt, schema


def draft_sub_availability(
    conn: sqlite3.Connection, provider: Provider, prospect: sqlite3.Row | None, date: str
) -> dict:
    system, prompt, schema = build_sub_availability_prompt(conn, prospect, date)
    raw_result, used_provider = run(provider, system, prompt, schema)
    result = _normalize(raw_result)
    drafts_service.save_draft(
        conn,
        kind=SUB_AVAILABILITY_KIND,
        ref_kind="prospect" if prospect is not None else None,
        ref_id=prospect["id"] if prospect is not None else None,
        provider=used_provider,
        content={**result, "date": date},
    )
    return {**result, "provider": used_provider, "date": date}


def latest_followup(conn: sqlite3.Connection, prospect_id: int) -> sqlite3.Row | None:
    return drafts_service.latest_draft(
        conn, kind=FOLLOWUP_KIND, ref_kind="prospect", ref_id=prospect_id
    )
