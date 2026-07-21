-- 0004_requirements_vault.sql — M3 requirements parser + asset vault +
-- kit builder + repertoire list builder (PLAN.md §5/§12 M3).
--
-- assets/requirements/kit_tasks already exist (0001); this adds an index
-- for the vault's per-kind listing and matching queries, plus a table for
-- the repertoire list builder's individual songs (tagged by occasion —
-- PLAN.md §5 lists "repertoire list" as a single vault asset, but the
-- builder that produces it needs its own rows; see vamp/vault/repertoire.py).

CREATE INDEX idx_assets_kind ON assets(kind);
CREATE INDEX idx_kit_tasks_ord ON kit_tasks(ord);

CREATE TABLE repertoire_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    artist      TEXT,
    occasions   TEXT,  -- comma-separated: wedding,cocktail,worship,jazz,originals,improv
    notes       TEXT,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
