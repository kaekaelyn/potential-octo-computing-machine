-- 0005_prospects_engine.sql — M4 prospects engine + OKC seed data
-- (PLAN.md §6/§12 M4).
--
-- The prospects/touches/scene_events/patrol_items/playbooks/reminders tables
-- already exist (0001). This migration adds the columns the cadence engine and
-- playbook execution need, plus the rate-range reference table that the rate
-- ranges seed dataset (PLAN.md §8) loads into.
--
--   * prospects.cooldown_days  — per-prospect outreach cooldown override; the
--     cadence engine falls back to a global default when NULL (PLAN.md §13
--     "per-prospect cooldowns").
--   * prospects.playbook / scene_events.playbook — link a seeded prospect or
--     scene event to the playbook whose strategy it executes (PLAN.md §6:
--     "each is a short written strategy plus the pre-seeded prospects/
--     scene-events to execute it").
--   * rate_ranges — researched OKC-market rate ranges by gig type, verified
--     during the build like every other seed row (PLAN.md §8 / §10 addendum).

ALTER TABLE prospects ADD COLUMN cooldown_days INTEGER;
ALTER TABLE prospects ADD COLUMN playbook TEXT;

ALTER TABLE scene_events ADD COLUMN playbook TEXT;

CREATE INDEX idx_prospects_status ON prospects(status);
CREATE INDEX idx_prospects_next_touch_at ON prospects(next_touch_at);

CREATE TABLE rate_ranges (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    gig_type    TEXT NOT NULL,      -- e.g. "solo cocktail hour", "wedding ceremony"
    low         REAL,               -- low end of the researched market range (USD)
    high        REAL,               -- high end (USD)
    unit        TEXT,               -- flat|hour|set|event|month|service
    area        TEXT,               -- market the range describes (default OKC metro)
    notes       TEXT,
    source      TEXT,               -- where the range came from (URL or citation)
    verified    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_rate_ranges_gig_type ON rate_ranges(gig_type);
