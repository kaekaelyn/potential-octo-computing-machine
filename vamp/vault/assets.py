"""Asset vault CRUD: bios, headshots, live videos, audio demos, repertoire
list, CV, references, tech rider, rate card, EPK (PLAN.md §5) — tagged,
dated, file-or-URL storage.

Uploaded files live under ``~/.vamp/assets/<kind>/`` (private Termux
storage per CLAUDE.md); a bare URL is stored as-is. ``path_or_url`` is
used to distinguish the two at read time via ``is_local_file``.
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

from vamp.vault.matching import rematch_requirements_for_asset_kind


def assets_dir(vamp_home: Path) -> Path:
    d = vamp_home / "assets"
    d.mkdir(parents=True, exist_ok=True)
    return d


def is_local_file(path_or_url: str | None) -> bool:
    if not path_or_url:
        return False
    return not (path_or_url.startswith("http://") or path_or_url.startswith("https://"))


def list_assets(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM assets ORDER BY kind, updated_at DESC, id DESC").fetchall()


def get_asset(conn: sqlite3.Connection, asset_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()


def _store_file(vamp_home: Path, kind: str, filename: str, data: bytes) -> str:
    dest_dir = assets_dir(vamp_home) / kind
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex}_{Path(filename).name}"
    dest = dest_dir / safe_name
    dest.write_bytes(data)
    return str(dest)


def create_asset(
    conn: sqlite3.Connection,
    vamp_home: Path,
    *,
    kind: str,
    name: str,
    url: str = "",
    file_name: str | None = None,
    file_bytes: bytes | None = None,
    tags: str = "",
    ready: bool = False,
) -> int:
    if file_name and file_bytes:
        path_or_url = _store_file(vamp_home, kind, file_name, file_bytes)
    else:
        path_or_url = url.strip() or None

    cur = conn.execute(
        "INSERT INTO assets (kind, name, path_or_url, tags, ready) VALUES (?, ?, ?, ?, ?)",
        (kind, name, path_or_url, tags.strip(), int(ready)),
    )
    conn.commit()
    rematch_requirements_for_asset_kind(conn, kind)
    return cur.lastrowid


def update_asset(
    conn: sqlite3.Connection,
    vamp_home: Path,
    asset_id: int,
    *,
    kind: str,
    name: str,
    url: str = "",
    file_name: str | None = None,
    file_bytes: bytes | None = None,
    tags: str = "",
    ready: bool = False,
) -> None:
    existing = get_asset(conn, asset_id)
    if existing is None:
        return
    if file_name and file_bytes:
        path_or_url = _store_file(vamp_home, kind, file_name, file_bytes)
    elif url.strip():
        path_or_url = url.strip()
    else:
        path_or_url = existing["path_or_url"]

    old_kind = existing["kind"]
    conn.execute(
        "UPDATE assets SET kind=?, name=?, path_or_url=?, tags=?, ready=?, "
        "updated_at=datetime('now') WHERE id=?",
        (kind, name, path_or_url, tags.strip(), int(ready), asset_id),
    )
    conn.commit()
    rematch_requirements_for_asset_kind(conn, old_kind)
    if kind != old_kind:
        rematch_requirements_for_asset_kind(conn, kind)


def toggle_ready(conn: sqlite3.Connection, asset_id: int) -> None:
    row = get_asset(conn, asset_id)
    if row is None:
        return
    conn.execute(
        "UPDATE assets SET ready = ?, updated_at = datetime('now') WHERE id = ?",
        (0 if row["ready"] else 1, asset_id),
    )
    conn.commit()
    rematch_requirements_for_asset_kind(conn, row["kind"])


def delete_asset(conn: sqlite3.Connection, asset_id: int) -> None:
    row = get_asset(conn, asset_id)
    if row is None:
        return
    conn.execute(
        "UPDATE requirements SET satisfied_asset_id = NULL WHERE satisfied_asset_id = ?",
        (asset_id,),
    )
    conn.execute("DELETE FROM assets WHERE id = ?", (asset_id,))
    conn.commit()
    rematch_requirements_for_asset_kind(conn, row["kind"])
