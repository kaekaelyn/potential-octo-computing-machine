"""Maps a ``sources`` row to a configured adapter instance.

Adapter-specific config (queries, feed URLs, CSS selectors...) lives in the
row's ``config_json``; secrets (API keys) live in ``~/.vamp/env`` (CLAUDE.md
"Secrets ... in ~/.vamp/env, mode 600") and are threaded in from the app's
``Config`` object, never stored in the database.
"""

from __future__ import annotations

import json
import sqlite3

from vamp.config import Config
from vamp.sources.adzuna import DEFAULT_QUERIES as ADZUNA_DEFAULT_QUERIES
from vamp.sources.adzuna import DEFAULT_RADIUS_MILES, DEFAULT_WHERE, AdzunaAdapter, AdzunaConfig
from vamp.sources.base import SourceAdapter
from vamp.sources.page_watcher import PageWatchConfig, PageWatcherAdapter
from vamp.sources.rss import RssAdapter, RssConfig
from vamp.sources.usajobs import DEFAULT_KEYWORDS as USAJOBS_DEFAULT_KEYWORDS
from vamp.sources.usajobs import MUSIC_SPECIALIST_SERIES, UsajobsAdapter, UsajobsConfig


def _last_page_hash(conn: sqlite3.Connection, source_id: int) -> str | None:
    row = conn.execute(
        "SELECT content_hash FROM source_state WHERE source_id = ?", (source_id,)
    ).fetchone()
    return row["content_hash"] if row else None


def build_adapter(
    vamp_config: Config, conn: sqlite3.Connection, source_row: sqlite3.Row
) -> SourceAdapter:
    kind = source_row["kind"]
    cfg = json.loads(source_row["config_json"] or "{}")

    if kind == "adzuna":
        return AdzunaAdapter(
            AdzunaConfig(
                app_id=vamp_config.get("ADZUNA_APP_ID"),
                app_key=vamp_config.get("ADZUNA_APP_KEY"),
                where=cfg.get("where", DEFAULT_WHERE),
                radius_miles=cfg.get("radius_miles", DEFAULT_RADIUS_MILES),
                queries=cfg.get("queries", list(ADZUNA_DEFAULT_QUERIES)),
            )
        )

    if kind == "usajobs":
        return UsajobsAdapter(
            UsajobsConfig(
                api_key=vamp_config.get("USAJOBS_API_KEY"),
                email=vamp_config.get("USAJOBS_EMAIL"),
                keywords=cfg.get("keywords", list(USAJOBS_DEFAULT_KEYWORDS)),
                job_category_code=cfg.get("job_category_code", MUSIC_SPECIALIST_SERIES),
                location_name=cfg.get("location_name"),
                radius_miles=cfg.get("radius_miles"),
            )
        )

    if kind == "rss":
        return RssAdapter(RssConfig(feed_url=cfg["feed_url"], name=source_row["name"]))

    if kind == "page_watch":
        return PageWatcherAdapter(
            PageWatchConfig(
                url=cfg["url"],
                name=source_row["name"],
                mode=cfg.get("mode", "diff"),
                selector=cfg.get("selector"),
                interval_seconds=source_row["interval_seconds"],
            ),
            last_hash=_last_page_hash(conn, source_row["id"]),
        )

    raise ValueError(f"unknown source kind: {kind!r}")
