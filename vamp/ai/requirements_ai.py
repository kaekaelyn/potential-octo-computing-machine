"""AI requirement extraction merged with the M3 heuristic pass (PLAN.md
§5/§9 priority #2): the regex parser in ``vamp.requirements.parser`` is
fast and always available, but a posting can phrase an ask in a way no
pattern anticipated. This pass re-reads a lead's text, and any requirement
kind it finds that the heuristic pass missed gets merged into the same
``requirements`` table — it only ever *adds* kinds, never removes or
overrides what the heuristic already found.

Cached per lead, keyed by a hash of the source text: an edited lead
(different text) is treated as needing a fresh pass; an unedited one is
never re-billed to the subscription twice.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3

from vamp.ai import drafts as drafts_service
from vamp.ai.provider import Provider
from vamp.ai.router import run
from vamp.requirements.kinds import REQUIREMENT_KINDS, REQUIREMENT_TO_ASSET_KIND
from vamp.vault.matching import best_asset_id

DRAFT_KIND = "requirement_extraction"

SYSTEM_PROMPT = (
    "You extract concrete application requirements from a musician gig/job "
    "posting. Only list things the posting actually asks the applicant to "
    "provide or do — do not invent requirements that aren't there."
)

SCHEMA_FIELDS = {
    "requirements": (
        'array of objects, each {"kind": one of '
        + ", ".join(REQUIREMENT_KINDS)
        + ', "detail": the matching sentence or phrase from the posting}. '
        "Empty array if the posting asks for nothing concrete."
    ),
}


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_prompt(text: str) -> tuple[str, str, dict]:
    prompt = f"Posting text:\n{text}"
    schema = {"task": "requirement_extraction", "fields": SCHEMA_FIELDS, "context": {"text": text}}
    return SYSTEM_PROMPT, prompt, schema


def _normalize(result: dict) -> list[dict]:
    raw = result.get("requirements")
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        if kind not in REQUIREMENT_KINDS:
            continue
        out.append({"kind": kind, "detail": str(item.get("detail") or "")[:200]})
    return out


def _merge_into_requirements(
    conn: sqlite3.Connection, lead_id: int, ai_requirements: list[dict]
) -> int:
    existing_kinds = {
        row["kind"]
        for row in conn.execute("SELECT kind FROM requirements WHERE lead_id = ?", (lead_id,))
    }
    added = 0
    for req in ai_requirements:
        if req["kind"] in existing_kinds:
            continue
        asset_kind = REQUIREMENT_TO_ASSET_KIND.get(req["kind"])
        asset_id = best_asset_id(conn, asset_kind) if asset_kind else None
        conn.execute(
            "INSERT INTO requirements (lead_id, kind, detail, satisfied_asset_id) "
            "VALUES (?, ?, ?, ?)",
            (lead_id, req["kind"], req["detail"], asset_id),
        )
        existing_kinds.add(req["kind"])
        added += 1
    conn.commit()
    return added


def extract_and_merge(conn: sqlite3.Connection, provider: Provider, lead: sqlite3.Row) -> dict:
    """Run (or reuse the cached) AI extraction for one lead and merge any
    new requirement kinds into ``requirements``. Never raises."""
    text = f"{lead['title']}\n{lead['description'] or ''}"
    text_hash = _text_hash(text)

    cached = drafts_service.latest_draft(conn, kind=DRAFT_KIND, ref_kind="lead", ref_id=lead["id"])
    if cached is not None:
        payload = json.loads(cached["content_json"])
        if payload.get("text_hash") == text_hash:
            added = _merge_into_requirements(conn, lead["id"], payload.get("requirements", []))
            return {**payload, "provider": cached["provider"], "added": added}

    system, prompt, schema = build_prompt(text)
    raw_result, used_provider = run(provider, system, prompt, schema)
    requirements = _normalize(raw_result)
    payload = {"text_hash": text_hash, "requirements": requirements}
    drafts_service.save_draft(
        conn,
        kind=DRAFT_KIND,
        ref_kind="lead",
        ref_id=lead["id"],
        provider=used_provider,
        content=payload,
    )
    added = _merge_into_requirements(conn, lead["id"], requirements)
    return {**payload, "provider": used_provider, "added": added}


def leads_needing_extraction(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Leads with no ``requirement_extraction`` draft at all yet. (A lead
    whose text changed after its first pass is caught by the hash check
    inside ``extract_and_merge``, not by this query — this is just the
    "brand new" queue for the nightly batch.)"""
    return conn.execute(
        """
        SELECT leads.* FROM leads
        LEFT JOIN drafts ON drafts.kind = ? AND drafts.ref_kind = 'lead'
            AND drafts.ref_id = leads.id
        WHERE leads.state != 'excluded' AND drafts.id IS NULL
        ORDER BY leads.first_seen_at ASC
        """,
        (DRAFT_KIND,),
    ).fetchall()


def extract_for_new_leads(conn: sqlite3.Connection, provider: Provider) -> list[dict]:
    results = []
    for lead in leads_needing_extraction(conn):
        results.append({"lead_id": lead["id"], **extract_and_merge(conn, provider, lead)})
    return results
