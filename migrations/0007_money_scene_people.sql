-- 0007_money_scene_people.sql — M6 money, follow-ups, scene, people
-- (PLAN.md §7/§8/§12 M6).
--
-- gigs/invoices/reminders/people/referrals/scene_events already exist
-- (0001) — this migration only adds the columns the M6 lifecycle and
-- cadence engine need, plus lookup indexes.
--
--   * gigs.played_at / gigs.paid_at — timestamps the lifecycle stamps on
--     the offered→confirmed→played→paid transitions (vamp/gigs/pipeline.py).
--     played_at anchors the chase-unpaid reminder at +14d (PLAN.md §8).
--   * gigs.strategic / leads.strategic — PLAN.md §8: "leads and drafts
--     [i.e. gigs not yet played — the pay figure is still a draft
--     agreement, not money in hand] below floor get a below-floor chip
--     unless flagged strategic." A human override so a below-floor booking
--     taken deliberately (a foothold, a favor for a referring planner)
--     doesn't keep nagging.
--   * scene_events.last_recap_at — the date of the most recent occurrence
--     already asked about ("met anyone?"), so the recap reminder fires
--     once per occurrence instead of every time the page loads
--     (vamp/scene/cadence.py).

ALTER TABLE gigs ADD COLUMN played_at TEXT;
ALTER TABLE gigs ADD COLUMN paid_at TEXT;
ALTER TABLE gigs ADD COLUMN strategic INTEGER NOT NULL DEFAULT 0;

ALTER TABLE leads ADD COLUMN strategic INTEGER NOT NULL DEFAULT 0;

ALTER TABLE scene_events ADD COLUMN last_recap_at TEXT;

CREATE INDEX idx_gigs_state ON gigs(state);
CREATE INDEX idx_gigs_date ON gigs(date);
CREATE INDEX idx_invoices_gig_id ON invoices(gig_id);
CREATE INDEX idx_reminders_ref ON reminders(ref_kind, ref_id);
CREATE INDEX idx_reminders_due ON reminders(due_at, done);
CREATE INDEX idx_referrals_person_id ON referrals(person_id);
CREATE INDEX idx_referrals_gig_id ON referrals(gig_id);
