-- 0003_sources_scheduling.sql — M2 feeds + watchers.
-- Adds per-source poll interval and last-success tracking (last_fetch_at from
-- 0001 is "last attempt"; last_success_at distinguishes attempts from
-- successes on the /sources admin page), plus a small state table for
-- adapters that need to remember something between polls (the page-watcher's
-- content hash for diff/CSS-selector change detection).

ALTER TABLE sources ADD COLUMN interval_seconds INTEGER NOT NULL DEFAULT 3600;
ALTER TABLE sources ADD COLUMN last_success_at TEXT;

CREATE TABLE source_state (
    source_id     INTEGER PRIMARY KEY REFERENCES sources(id),
    content_hash  TEXT,
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
