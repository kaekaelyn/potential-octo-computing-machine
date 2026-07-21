"""Repertoire list builder: individual songs tagged by occasion (wedding/
cocktail/worship/jazz/originals/improv — PLAN.md §5), compiled into the
vault's single ``repertoire_list`` asset so it participates in
READY/Missing matching like any other asset.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from vamp.vault.matching import rematch_requirements_for_asset_kind

OCCASIONS: tuple[str, ...] = ("wedding", "cocktail", "worship", "jazz", "originals", "improv")

_COMPILED_FILENAME = "repertoire.txt"


def list_items(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM repertoire_items ORDER BY title COLLATE NOCASE").fetchall()


def _occasions_csv(occasions: list[str]) -> str:
    return ",".join(o for o in occasions if o in OCCASIONS)


def add_item(
    conn: sqlite3.Connection,
    vamp_home: Path,
    *,
    title: str,
    artist: str = "",
    occasions: list[str] | None = None,
    notes: str = "",
) -> int:
    cur = conn.execute(
        "INSERT INTO repertoire_items (title, artist, occasions, notes) VALUES (?, ?, ?, ?)",
        (
            title.strip(),
            artist.strip() or None,
            _occasions_csv(occasions or []),
            notes.strip() or None,
        ),
    )
    conn.commit()
    _sync_asset(conn, vamp_home)
    return cur.lastrowid


def update_item(
    conn: sqlite3.Connection,
    vamp_home: Path,
    item_id: int,
    *,
    title: str,
    artist: str = "",
    occasions: list[str] | None = None,
    notes: str = "",
) -> None:
    conn.execute(
        "UPDATE repertoire_items SET title=?, artist=?, occasions=?, notes=?, "
        "updated_at=datetime('now') WHERE id=?",
        (
            title.strip(),
            artist.strip() or None,
            _occasions_csv(occasions or []),
            notes.strip() or None,
            item_id,
        ),
    )
    conn.commit()
    _sync_asset(conn, vamp_home)


def delete_item(conn: sqlite3.Connection, vamp_home: Path, item_id: int) -> None:
    conn.execute("DELETE FROM repertoire_items WHERE id = ?", (item_id,))
    conn.commit()
    _sync_asset(conn, vamp_home)


def compile_text(items: list[sqlite3.Row]) -> str:
    lines: list[str] = []
    tagged_ids: set[int] = set()
    for occasion in OCCASIONS:
        tagged = [i for i in items if occasion in (i["occasions"] or "").split(",")]
        if not tagged:
            continue
        lines.append(f"{occasion.capitalize()}:")
        for item in tagged:
            tagged_ids.add(item["id"])
            suffix = f" — {item['artist']}" if item["artist"] else ""
            lines.append(f"  - {item['title']}{suffix}")
        lines.append("")

    untagged = [i for i in items if i["id"] not in tagged_ids]
    if untagged:
        lines.append("Other:")
        for item in untagged:
            suffix = f" — {item['artist']}" if item["artist"] else ""
            lines.append(f"  - {item['title']}{suffix}")

    return "\n".join(lines).strip()


def _sync_asset(conn: sqlite3.Connection, vamp_home: Path) -> None:
    """Write the compiled list to the vault's ``repertoire_list`` asset —
    ready once at least one song is entered, tagged with the occasions in
    use."""
    from vamp.vault.assets import assets_dir

    items = list_items(conn)
    compiled = compile_text(items)
    occasions_used = sorted({o for i in items for o in (i["occasions"] or "").split(",") if o})
    tags = ",".join(occasions_used)
    ready = 1 if items else 0

    dest_dir = assets_dir(vamp_home) / "repertoire_list"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / _COMPILED_FILENAME
    dest.write_text(compiled)

    existing = conn.execute("SELECT id FROM assets WHERE kind = 'repertoire_list'").fetchone()
    if existing:
        conn.execute(
            "UPDATE assets SET name=?, path_or_url=?, tags=?, ready=?, updated_at=datetime('now') "
            "WHERE id=?",
            ("Repertoire list", str(dest), tags, ready, existing["id"]),
        )
    else:
        conn.execute(
            "INSERT INTO assets (kind, name, path_or_url, tags, ready) VALUES "
            "('repertoire_list', ?, ?, ?, ?)",
            ("Repertoire list", str(dest), tags, ready),
        )
    conn.commit()
    rematch_requirements_for_asset_kind(conn, "repertoire_list")
