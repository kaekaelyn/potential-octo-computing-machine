"""Shared cache read/write for the ``scores`` and ``drafts`` tables — every
AI output lands in one of these two, keyed so nothing gets scored or
drafted twice for the same input (CLAUDE.md: "caching of all outputs in
scores/drafts tables")."""

from __future__ import annotations

import json
import sqlite3


def save_score(conn: sqlite3.Connection, lead_id: int, scorer: str, result: dict) -> None:
    conn.execute(
        "INSERT INTO scores (lead_id, scorer, score, rationale_json, scored_at) "
        "VALUES (?, ?, ?, ?, datetime('now')) "
        "ON CONFLICT (lead_id, scorer) DO UPDATE SET "
        "score = excluded.score, rationale_json = excluded.rationale_json, "
        "scored_at = excluded.scored_at",
        (lead_id, scorer, result.get("score"), json.dumps(result)),
    )
    conn.commit()


def get_scores(conn: sqlite3.Connection, lead_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM scores WHERE lead_id = ? ORDER BY scored_at DESC", (lead_id,)
    ).fetchall()


def latest_score(conn: sqlite3.Connection, lead_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM scores WHERE lead_id = ? ORDER BY scored_at DESC LIMIT 1", (lead_id,)
    ).fetchone()


def has_score(conn: sqlite3.Connection, lead_id: int) -> bool:
    return (
        conn.execute("SELECT 1 FROM scores WHERE lead_id = ? LIMIT 1", (lead_id,)).fetchone()
        is not None
    )


def save_draft(
    conn: sqlite3.Connection,
    *,
    kind: str,
    ref_kind: str | None,
    ref_id: int | None,
    provider: str,
    content: dict,
) -> int:
    cur = conn.execute(
        "INSERT INTO drafts (kind, ref_kind, ref_id, provider, content_json) "
        "VALUES (?, ?, ?, ?, ?)",
        (kind, ref_kind, ref_id, provider, json.dumps(content)),
    )
    conn.commit()
    return cur.lastrowid


def latest_draft(
    conn: sqlite3.Connection, *, kind: str, ref_kind: str | None, ref_id: int | None
) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM drafts WHERE kind = ? AND ref_kind IS ? AND ref_id IS ? "
        "ORDER BY created_at DESC, id DESC LIMIT 1",
        (kind, ref_kind, ref_id),
    ).fetchone()


def list_drafts(
    conn: sqlite3.Connection, *, kind: str, ref_kind: str | None, ref_id: int | None
) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM drafts WHERE kind = ? AND ref_kind IS ? AND ref_id IS ? "
        "ORDER BY created_at DESC, id DESC",
        (kind, ref_kind, ref_id),
    ).fetchall()


def has_draft(
    conn: sqlite3.Connection, *, kind: str, ref_kind: str | None, ref_id: int | None
) -> bool:
    return latest_draft(conn, kind=kind, ref_kind=ref_kind, ref_id=ref_id) is not None
