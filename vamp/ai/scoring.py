"""Lead scoring (PLAN.md §4/§9): 0-100 with a rationale and red-flag chips,
heuristic always, AI on top when available. This is priority #1 of the AI
feature list in PLAN.md §9 and the subject of M5's "queued, batched nightly
scoring of new leads."
"""

from __future__ import annotations

import sqlite3

from vamp.ai import drafts as drafts_service
from vamp.ai.provider import Provider
from vamp.ai.router import run

SYSTEM_PROMPT = (
    "You help a working musician (pianist/vocalist/improviser) in the Oklahoma "
    "City metro triage paid-gig leads. Score how worth pursuing this one is."
)

SCHEMA_FIELDS = {
    "score": "integer 0-100, higher is more worth pursuing",
    "rationale": "one or two sentences explaining the score",
    "flags": "array of short red-flag strings, e.g. 'ghost-gig-risk', 'below-market', "
    "'pay-to-play-risk' (empty array if none)",
}


def _lead_context(lead: sqlite3.Row) -> dict:
    return {
        "title": lead["title"],
        "org": lead["org"],
        "location": lead["location"],
        "description": lead["description"],
        "pay_kind": lead["pay_kind"],
        "pay_min": lead["pay_min"],
        "pay_max": lead["pay_max"],
        "deadline": lead["deadline"],
        "event_date": lead["event_date"],
        "kind": lead["kind"],
    }


def build_prompt(lead: sqlite3.Row) -> tuple[str, str, dict]:
    ctx = _lead_context(lead)
    prompt = (
        f"Title: {ctx['title']}\n"
        f"Org: {ctx['org'] or 'unknown'}\n"
        f"Location: {ctx['location'] or 'unknown'}\n"
        f"Pay: {ctx['pay_kind']} "
        f"({ctx['pay_min'] or '?'}-{ctx['pay_max'] or '?'})\n"
        f"Deadline: {ctx['deadline'] or 'none'}\n"
        f"Event date: {ctx['event_date'] or 'none'}\n"
        f"Description:\n{ctx['description'] or ''}"
    )
    schema = {"task": "score_lead", "fields": SCHEMA_FIELDS, "context": ctx}
    return SYSTEM_PROMPT, prompt, schema


def _normalize(result: dict) -> dict:
    score = result.get("score")
    try:
        score = max(0, min(100, int(score)))
    except (TypeError, ValueError):
        score = None
    flags = result.get("flags")
    if not isinstance(flags, list):
        flags = []
    return {
        "score": score,
        "rationale": str(result.get("rationale") or ""),
        "flags": [str(f) for f in flags],
    }


def score_lead(conn: sqlite3.Connection, provider: Provider, lead: sqlite3.Row) -> dict:
    """Score one lead and cache the result under ``scores`` keyed by the
    provider that actually produced it. Never raises."""
    system, prompt, schema = build_prompt(lead)
    raw_result, used_provider = run(provider, system, prompt, schema)
    result = _normalize(raw_result)
    drafts_service.save_score(conn, lead["id"], used_provider, result)
    return {**result, "provider": used_provider}


def unscored_leads(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Leads that have never been scored by any provider — the nightly
    batch's queue (PLAN.md §9: "nothing is scored twice")."""
    return conn.execute(
        "SELECT leads.* FROM leads "
        "LEFT JOIN scores ON scores.lead_id = leads.id "
        "WHERE leads.state != 'excluded' AND scores.lead_id IS NULL "
        "GROUP BY leads.id "
        "ORDER BY leads.first_seen_at ASC"
    ).fetchall()


def score_new_leads(conn: sqlite3.Connection, provider: Provider) -> list[dict]:
    results = []
    for lead in unscored_leads(conn):
        results.append({"lead_id": lead["id"], **score_lead(conn, provider, lead)})
    return results
