-- 0001_init.sql — initial schema, per PLAN.md §10.
-- Never edit this file after it has shipped; add a new numbered migration
-- instead (see vamp/db.py).

CREATE TABLE sources (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    kind           TEXT NOT NULL,
    name           TEXT NOT NULL,
    config_json    TEXT NOT NULL DEFAULT '{}',
    enabled        INTEGER NOT NULL DEFAULT 1,
    last_fetch_at  TEXT,
    last_error     TEXT
);

CREATE TABLE leads (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id        INTEGER REFERENCES sources(id),
    kind             TEXT NOT NULL, -- gig|job|competition|open_mic|showcase|other
    dedupe_hash      TEXT NOT NULL,
    url              TEXT,
    title            TEXT NOT NULL,
    org              TEXT,
    location         TEXT,
    pay_min          REAL,
    pay_max          REAL,
    pay_kind         TEXT, -- flat|hourly|salary|tips|unpaid|unknown
    deadline         TEXT,
    event_date       TEXT,
    description      TEXT,
    posted_at        TEXT,
    first_seen_at    TEXT NOT NULL DEFAULT (datetime('now')),
    state            TEXT NOT NULL DEFAULT 'inbox', -- inbox|interested|preparing|applied|booked|passed|excluded
    excluded_reason  TEXT,
    raw_json         TEXT
);
CREATE INDEX idx_leads_dedupe_hash ON leads(dedupe_hash);
CREATE INDEX idx_leads_state ON leads(state);

CREATE TABLE requirements (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id             INTEGER NOT NULL REFERENCES leads(id),
    kind                TEXT NOT NULL,
    detail              TEXT,
    satisfied_asset_id  INTEGER REFERENCES assets(id)
);
CREATE INDEX idx_requirements_lead_id ON requirements(lead_id);

CREATE TABLE assets (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    kind           TEXT NOT NULL,
    name           TEXT NOT NULL,
    path_or_url    TEXT,
    tags           TEXT,
    updated_at     TEXT NOT NULL DEFAULT (datetime('now')),
    ready          INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE kit_tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ord         INTEGER NOT NULL,
    title       TEXT NOT NULL,
    detail      TEXT,
    asset_kind  TEXT,
    state       TEXT NOT NULL DEFAULT 'todo'
);

CREATE TABLE prospects (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,
    category       TEXT,
    area           TEXT,
    address        TEXT,
    phone          TEXT,
    email          TEXT,
    website        TEXT,
    socials_json   TEXT,
    has_piano      INTEGER,
    angle          TEXT,
    status         TEXT NOT NULL DEFAULT 'identified',
    source         TEXT,
    verified       INTEGER NOT NULL DEFAULT 0,
    notes          TEXT,
    last_touch_at  TEXT,
    next_touch_at  TEXT
);

CREATE TABLE touches (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id  INTEGER NOT NULL REFERENCES prospects(id),
    ts           TEXT NOT NULL DEFAULT (datetime('now')),
    channel      TEXT,
    summary      TEXT,
    outcome      TEXT
);
CREATE INDEX idx_touches_prospect_id ON touches(prospect_id);

CREATE TABLE people (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    role          TEXT,
    org           TEXT,
    met_at        TEXT,
    contact_json  TEXT,
    notes         TEXT
);

CREATE TABLE referrals (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id  INTEGER NOT NULL REFERENCES people(id),
    gig_id     INTEGER NOT NULL REFERENCES gigs(id)
);

CREATE TABLE scene_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    cadence_json  TEXT,
    venue         TEXT,
    area          TEXT,
    url           TEXT,
    kind          TEXT,
    notes         TEXT,
    going         INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE patrol_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    url             TEXT,
    notes           TEXT,
    last_checked_at TEXT
);

CREATE TABLE gigs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id   INTEGER REFERENCES prospects(id),
    lead_id       INTEGER REFERENCES leads(id),
    date          TEXT,
    venue         TEXT,
    pay_agreed    REAL,
    pay_received  REAL,
    expenses      REAL,
    mileage       REAL,
    state         TEXT NOT NULL DEFAULT 'offered', -- offered|confirmed|played|paid
    notes         TEXT
);

CREATE TABLE invoices (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    gig_id     INTEGER NOT NULL REFERENCES gigs(id),
    number     TEXT NOT NULL UNIQUE,
    issued_at  TEXT,
    paid_at    TEXT,
    amount     REAL,
    html_path  TEXT
);

CREATE TABLE playbooks (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    slug           TEXT NOT NULL UNIQUE,
    title          TEXT NOT NULL,
    body_md        TEXT,
    active_months  TEXT
);

CREATE TABLE scores (
    lead_id         INTEGER NOT NULL REFERENCES leads(id),
    scorer          TEXT NOT NULL,
    score           REAL,
    rationale_json  TEXT,
    scored_at       TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (lead_id, scorer)
);

CREATE TABLE reminders (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ref_kind  TEXT NOT NULL,
    ref_id    INTEGER NOT NULL,
    due_at    TEXT NOT NULL,
    message   TEXT,
    done      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE profile (
    key    TEXT PRIMARY KEY,
    value  TEXT
);

CREATE TABLE events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT NOT NULL DEFAULT (datetime('now')),
    kind         TEXT NOT NULL,
    payload_json TEXT
);
