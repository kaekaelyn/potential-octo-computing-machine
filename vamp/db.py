"""SQLite (WAL) connection + minimal numbered-SQL-file migration runner.

CLAUDE.md: "schema changes = new numbered SQL file in migrations/, applied
by the built-in runner. Never edit old migrations."
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = REPO_ROOT / "migrations"


def connect(db_path: Path) -> sqlite3.Connection:
    """Open a WAL-mode SQLite connection, creating the parent dir if needed."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "id TEXT PRIMARY KEY, "
        "applied_at TEXT NOT NULL DEFAULT (datetime('now')))"
    )
    conn.commit()


def applied_migrations(conn: sqlite3.Connection) -> set[str]:
    _ensure_migrations_table(conn)
    return {row["id"] for row in conn.execute("SELECT id FROM schema_migrations")}


def pending_migration_files(migrations_dir: Path = MIGRATIONS_DIR) -> list[Path]:
    return sorted(migrations_dir.glob("*.sql"))


def migrate(conn: sqlite3.Connection, migrations_dir: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply any migration files not yet recorded in schema_migrations.

    Returns the names of migrations applied this call (empty if already
    up to date). Safe to call on every connection open.
    """
    already_applied = applied_migrations(conn)
    newly_applied: list[str] = []
    for path in pending_migration_files(migrations_dir):
        if path.name in already_applied:
            continue
        conn.executescript(path.read_text())
        conn.execute("INSERT INTO schema_migrations (id) VALUES (?)", (path.name,))
        conn.commit()
        newly_applied.append(path.name)
    return newly_applied


def get_connection(db_path: Path, migrations_dir: Path = MIGRATIONS_DIR) -> sqlite3.Connection:
    """Open a connection with the schema migrated up to date."""
    conn = connect(db_path)
    migrate(conn, migrations_dir)
    return conn
