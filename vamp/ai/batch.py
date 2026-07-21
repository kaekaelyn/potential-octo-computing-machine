"""The nightly batch job (PLAN.md §9: "Calls are queued and batched...to
respect subscription limits and phone battery"): scores every new lead,
gives excluded degree-wall leads a second opinion, and runs AI requirement
extraction on new leads — one provider selection for the whole run rather
than one per item, and a single ``events`` row summarizing what happened.
"""

from __future__ import annotations

import json
import sqlite3

from vamp.ai import degree_review, requirements_ai, scoring
from vamp.ai.provider import Provider
from vamp.ai.router import get_provider
from vamp.config import Config


def run_nightly(
    conn: sqlite3.Connection, vamp_config: Config, provider: Provider | None = None
) -> dict:
    """Never raises — every sub-step already degrades to heuristics on its
    own; this just orchestrates and logs the summary."""
    provider = provider or get_provider(vamp_config)

    scored = scoring.score_new_leads(conn, provider)
    degree_reviewed = degree_review.review_pending_degree_exclusions(conn, provider)
    extracted = requirements_ai.extract_for_new_leads(conn, provider)

    summary = {
        "scored": len(scored),
        "degree_reviewed": len(degree_reviewed),
        "degree_overridden": sum(1 for r in degree_reviewed if r.get("override")),
        "requirements_extracted": len(extracted),
        "requirements_added": sum(r.get("added", 0) for r in extracted),
        "providers_used": sorted(
            {
                r.get("provider")
                for r in (*scored, *degree_reviewed, *extracted)
                if r.get("provider")
            }
        ),
    }
    conn.execute(
        "INSERT INTO events (kind, payload_json) VALUES ('ai_nightly_run', ?)",
        (json.dumps(summary),),
    )
    conn.commit()
    return summary
