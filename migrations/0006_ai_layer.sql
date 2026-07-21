-- 0006_ai_layer.sql — M5 AI layer (PLAN.md §9/§12 M5).
--
-- scores already exists (0001) — AI scoring UPSERTs rows keyed by
-- (lead_id, scorer), scorer being the provider name that actually produced
-- the row ('claude' or 'none'), so a re-score replaces the cached row
-- instead of duplicating it (PLAN.md §9: "nothing is scored twice").
--
-- drafts is new: every AI-drafted artifact (pitch, bio, follow-up note,
-- sub-availability note, requirement extraction, degree second-opinion) is
-- cached here rather than re-generated on every page view or nightly run
-- (CLAUDE.md: "caching of all outputs in scores/drafts tables").

CREATE TABLE drafts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    kind          TEXT NOT NULL,   -- pitch|bio|followup|sub_availability|
                                    -- requirement_extraction|degree_review
    ref_kind      TEXT,            -- prospect|lead|profile
    ref_id        INTEGER,
    provider      TEXT NOT NULL,   -- claude|none
    content_json  TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_drafts_kind_ref ON drafts(kind, ref_kind, ref_id);
