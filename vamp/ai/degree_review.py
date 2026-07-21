"""AI second-opinion pass for the degree filter (PLAN.md §4/§9): "this is
exactly the kind of nuance-reading a cheap AI call is good at." The M1
heuristic (``vamp.filters.degree``) is a blunt sentence-level pattern match;
this pass re-reads a degree-walled posting's full text and can lift the
wall when the requirement is clearly softer than the heuristic could tell
(e.g. "prefer a degree" phrased in a way the regex missed as a carve-out).

It never *adds* an exclusion the heuristic didn't already make — only ever
opens a wall the heuristic slammed shut, and only ever on a fresh lead
(cached in ``drafts`` so a lead is reviewed once, not every night).
"""

from __future__ import annotations

import json
import sqlite3

from vamp.ai import drafts as drafts_service
from vamp.ai.provider import Provider
from vamp.ai.router import run
from vamp.filters.degree import REASON as DEGREE_REASON

DRAFT_KIND = "degree_review"

SYSTEM_PROMPT = (
    "You help a working musician's lead-triage tool double-check an automated "
    "filter. A heuristic flagged this posting as requiring a music degree with "
    "no 'or equivalent experience' carve-out, excluding it. Read the full "
    "posting text and decide whether that's actually true, or whether the "
    "language is softer than the heuristic could tell (e.g. 'preferred' not "
    "'required', or an implicit equivalent-experience allowance)."
)

SCHEMA_FIELDS = {
    "override": "true if the degree wall should be LIFTED (the requirement is not "
    "actually a hard, no-exceptions degree requirement); false to leave it excluded",
    "reasoning": "one or two sentences explaining the decision",
}


def build_prompt(text: str) -> tuple[str, str, dict]:
    prompt = f"Posting text:\n{text}"
    schema = {"task": "degree_review", "fields": SCHEMA_FIELDS, "context": {"text": text}}
    return SYSTEM_PROMPT, prompt, schema


def _normalize(result: dict) -> dict:
    return {
        "override": bool(result.get("override")),
        "reasoning": str(result.get("reasoning") or ""),
    }


def review_lead(conn: sqlite3.Connection, provider: Provider, lead: sqlite3.Row) -> dict:
    """Run (or reuse the cached) second opinion for one degree-walled lead,
    lifting the wall (and restoring the lead, if no other exclusion reason
    remains) when the AI overrides it. Never raises."""
    cached = drafts_service.latest_draft(conn, kind=DRAFT_KIND, ref_kind="lead", ref_id=lead["id"])
    if cached is not None:
        return {**json.loads(cached["content_json"]), "provider": cached["provider"]}

    text = f"{lead['title']}\n{lead['description'] or ''}"
    system, prompt, schema = build_prompt(text)
    raw_result, used_provider = run(provider, system, prompt, schema)
    result = _normalize(raw_result)
    drafts_service.save_draft(
        conn,
        kind=DRAFT_KIND,
        ref_kind="lead",
        ref_id=lead["id"],
        provider=used_provider,
        content=result,
    )

    if result["override"]:
        _lift_degree_wall(conn, lead)

    return {**result, "provider": used_provider}


def _lift_degree_wall(conn: sqlite3.Connection, lead: sqlite3.Row) -> None:
    reasons = [r for r in (lead["excluded_reason"] or "").split(",") if r and r != DEGREE_REASON]
    if reasons:
        conn.execute(
            "UPDATE leads SET excluded_reason = ? WHERE id = ?",
            (",".join(reasons), lead["id"]),
        )
    else:
        conn.execute(
            "UPDATE leads SET state = 'inbox', excluded_reason = NULL WHERE id = ?",
            (lead["id"],),
        )
    conn.commit()


def pending_degree_reviews(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Excluded-for-degree-wall leads that haven't had a second opinion yet."""
    return conn.execute(
        """
        SELECT leads.* FROM leads
        LEFT JOIN drafts ON drafts.kind = ? AND drafts.ref_kind = 'lead'
            AND drafts.ref_id = leads.id
        WHERE leads.state = 'excluded'
          AND (',' || leads.excluded_reason || ',') LIKE ('%,' || ? || ',%')
          AND drafts.id IS NULL
        ORDER BY leads.first_seen_at ASC
        """,
        (DRAFT_KIND, DEGREE_REASON),
    ).fetchall()


def review_pending_degree_exclusions(conn: sqlite3.Connection, provider: Provider) -> list[dict]:
    results = []
    for lead in pending_degree_reviews(conn):
        results.append({"lead_id": lead["id"], **review_lead(conn, provider, lead)})
    return results
