-- 0002_capture_fields.sql — M1 capture support.
-- dedupe_hash (0001) already carries the fuzzy (org, title, event_date) key;
-- this adds the second dedupe key (canonical-URL hash) plus a flag for
-- leads that fell back to the "finish by hand" capture path.

ALTER TABLE leads ADD COLUMN url_hash TEXT;
ALTER TABLE leads ADD COLUMN needs_review INTEGER NOT NULL DEFAULT 0;

CREATE INDEX idx_leads_url_hash ON leads(url_hash);
