# Execution guide — building Vamp with AI coding sessions

The plan (PLAN.md) was produced with a frontier model (Fable).
Implementation runs as a series of **scoped sessions with less expensive
models**. This file is the playbook: per-milestone session prompts and
the model each stage runs on.

## Model assignments at a glance

| Milestone | Model | Why |
| --- | --- | --- |
| M0 Skeleton (Termux-first) | **Sonnet** (`claude-sonnet-5`) | Termux quirks (bionic, runit, boot hooks) need judgment; the rest is boilerplate |
| M1 Capture + leads inbox | **Sonnet** | share-target + parsing heuristics + filter logic; the day-one demo |
| M2 Feeds + watchers | **Sonnet** | adapter pattern is well-specified; scheduler resilience needs care |
| M3 Requirements + vault + kit | **Sonnet** | parser + matching logic, fixture-heavy |
| M4 Prospects + OKC seed data | **Opus** (`claude-opus-4-8`) | research-heavy: real venues, real contacts, verification judgment; the one stage where a stronger model earns its cost |
| M5 AI layer | **Sonnet** | proven Wingman pattern, adapted to Termux |
| M6 Money, scene, people | **Haiku** (`claude-haiku-4-5`) | pure CRUD with a tight spec; escalate to Sonnet after two failed runs |
| M7 Polish + phone ops | **Sonnet** | notification plumbing + docs quality |
| Review passes between milestones | **Sonnet** | `/code-review` or fresh session reviewing the diff vs. acceptance criteria |

## Why this split works

Planning is where deep judgment matters (ToS constraints, Termux
realities, outreach ethics, what actually gets a pianist paid in OKC).
Execution succeeds or fails on **scope and specification** — a mid-tier
model with a tight brief, fixtures, and acceptance criteria beats a
frontier model with a vague one. Every milestone below is sized to one
session, states its acceptance criteria, and names its surface area.

## Rules for every build session

1. **One milestone per session.** Stop at green acceptance criteria; do
   not start the next milestone.
2. **Start every session the same way:** read `CLAUDE.md`, `PLAN.md`,
   and this file's section for the current milestone before writing code.
3. **Tests are the contract.** Fixture-based tests for every adapter,
   parser, and filter; never live HTTP in tests.
4. **Demo script per milestone:** update `docs/DEMO.md` with the exact
   commands/taps to show it working. This is also the manual-QA script.
5. **Review between sessions** before starting the next milestone.
6. **Commit style:** small, imperative, milestone-tagged
   (`M2: add USAJOBS adapter`).
7. **When reality contradicts the plan,** update PLAN.md in the same
   commit. Drift between plan and code is a bug.
8. **Escalate model, not scope.** If a session fails a milestone twice,
   rerun it on the next model up (Haiku → Sonnet → Opus) rather than
   patching the prompt with hacks.
9. **The Termux gate:** any new dependency must be pure Python. If a
   session wants a compiled package, that's a design smell — find the
   pure-Python route or raise it in PLAN.md.
10. **The no-fabrication gate (M4 especially):** every seeded venue,
    contact, and date is either web-verified in-session or written with
    `verified: false`. A session must never invent an email address,
    phone number, or booking contact to complete a row.

## Session prompts

Paste verbatim to start each session, on the stated model, in this repo
with the designated branch checked out.

### M0 — Skeleton (model: Sonnet, `claude-sonnet-5`)

> Read CLAUDE.md, PLAN.md, and docs/EXECUTION.md §M0. Implement milestone
> M0 exactly as specified in PLAN.md §12: Python 3.11+ project named
> `vamp` using stdlib venv + pip with pinned requirements.txt (pure-Python
> deps only — no pydantic/lxml/uvloop/compiled packages), Flask app
> serving a placeholder dashboard at http://127.0.0.1:8485 behind
> waitress, SQLite schema from PLAN.md §10 created by a minimal
> numbered-SQL-file migration runner, config from `~/.vamp/env`,
> `install.sh` that detects Termux (`$TERMUX_VERSION`) and installs
> termux-services runit scripts + a Termux:Boot start script +
> termux-wake-lock, with a desktop-Linux dev fallback; Makefile with
> `dev`/`test`/`lint`; pytest + ruff configured; GitHub Actions workflow
> running lint+test; a CI check that fails if requirements.txt contains a
> known-compiled package. Acceptance: `make dev` serves the UI on desktop;
> `make test` green in CI; install.sh completes on both Termux and
> desktop paths (desktop verified, Termux path code-reviewed and
> documented in docs/PHONE.md). Update docs/DEMO.md. Do not start M1.

### M1 — Capture + leads inbox (model: Sonnet)

> Read CLAUDE.md, PLAN.md, and docs/EXECUTION.md §M1. Implement milestone
> M1: PWA manifest + service worker + Android share-target (POST target
> receiving shared URLs/text), paste-a-URL and paste-text capture in the
> UI, capture parser (JSON-LD JobPosting/Event, OpenGraph, heuristic
> fallback) that on fetch failure pre-fills a finish-by-hand lead form
> from the shared text (never errors out), `leads` table states, dedupe
> via normalized fuzzy hash + canonical URL, the three default-on hard
> filters (teaching; degree-required-without-equivalent-language;
> pay-to-play) implemented as testable pure functions with reason chips
> and a one-tap-restore Excluded shelf, the structural Paying vs
> Stepping-stones two-shelf inbox (unpaid never sorts into Paying), and
> the patrol checklist page (CRUD + last-checked ticks). Fixture tests:
> real posting texts proving teaching/degree exclusions including the
> "or equivalent" carve-out, pay-to-play detection, share-text parsing.
> Acceptance per PLAN.md §12 M1. Update docs/DEMO.md. Do not start M2.

### M2 — Feeds + watchers (model: Sonnet)

> Read CLAUDE.md, PLAN.md, and docs/EXECUTION.md §M2. Implement milestone
> M2: `Source` adapter protocol (`fetch() -> list[RawLead]`), Adzuna
> adapter (free API key, queries for musician/pianist/keyboardist/
> accompanist/"music director", Oklahoma City + configurable radius),
> USAJOBS adapter (military band / musician series), generic RSS adapter,
> and the polite page-watcher (per-page CSS-selector or diff mode,
> robots.txt respected, per-page interval ≥ 24h, hard-coded refusal
> blocklist for facebook/instagram/craigslist/indeed/linkedin domains).
> APScheduler with per-source intervals, jitter, and misfire grace;
> catch-up-on-open middleware that triggers overdue polls on any page
> load; `/sources` admin page (enable/disable, last fetch, last error);
> events rows for every fetch. Fixture tests per adapter; a raising
> adapter must not affect others (test this). New leads flow through the
> M1 filters automatically. Acceptance per PLAN.md §12 M2. Update
> docs/DEMO.md. Do not start M3.

### M3 — Requirements + vault + kit builder (model: Sonnet)

> Read CLAUDE.md, PLAN.md, and docs/EXECUTION.md §M3. Implement milestone
> M3: requirements parser decomposing lead text into the checklist kinds
> from PLAN.md §5 (heuristic patterns, fixture corpus of ≥15 real posting
> texts in tests/fixtures/), asset vault CRUD (kinds per PLAN.md §5,
> tags, ready flags, file-or-URL storage), READY/Missing badges on lead
> cards via requirement↔asset matching, the Unlock report ("which missing
> asset unlocks the most leads"), the kit-builder guided checklist
> (ordered kit_tasks seeded from PLAN.md §5: bios, headshots, three live
> videos, repertoire list, CV, tech rider, rate card, EPK), the
> repertoire list builder (tagged by occasion), EPK export as one
> self-contained static HTML file generated from the vault, and the
> `vamp backup` command (tarball DB + assets to Android shared storage
> with desktop fallback path). Acceptance per PLAN.md §12 M3. Update
> docs/DEMO.md. Do not start M4.

### M4 — Prospects engine + OKC seed data (model: Opus, `claude-opus-4-8`)

> Read CLAUDE.md, PLAN.md, and docs/EXECUTION.md §M4. Implement milestone
> M4 in two halves. (a) Code: prospects pipeline per PLAN.md §6 (states,
> angle field, touches log, cadence engine scheduling +7d/+21d follow-up
> reminders, per-prospect cooldowns, weekly Outreach Sprint aggregation),
> Overpass API importer (category × OKC-metro bounding queries, imported
> as verified:false), YAML seed loader (idempotent, in migrations flow).
> (b) Research: build the seed datasets in seeds/ — OKC-metro prospects
> by every category in PLAN.md §6 including the free-improv markets
> (dance programs/studios, museums, galleries, yoga, theaters),
> retirement communities, churches, planners; the scene calendar
> (recurring events, festivals + application windows); the patrol list
> of Facebook groups/pages; the competition deadline calendar; rate
> ranges; and the seven playbooks as markdown content. Use web search to
> verify every fact; anything unverifiable gets verified:false. NEVER
> invent a contact detail — leave the field empty instead. Acceptance:
> pipeline demo on a real prospect end-to-end; a 10-row random
> spot-check of seed data finds zero fabrications; playbooks render in
> the UI. Update docs/DEMO.md. Do not start M5.

### M5 — AI layer (model: Sonnet)

> Read CLAUDE.md, PLAN.md, and docs/EXECUTION.md §M5. Implement milestone
> M5: provider abstraction (`complete(system, prompt, schema) -> dict`)
> with `claude` (subprocess `claude -p --output-format json`) and `none`
> (heuristics/templates) implementations; health panel ("Claude: logged
> in ✓" / Termux fix instructions incl. nodejs-lts install); queued,
> batched nightly scoring of new leads; AI second-opinion pass for the
> degree filter; AI requirement extraction merging with M3 heuristics;
> pitch drafting per-prospect (vault + angle + voice sample from
> profile), bio drafting for the kit builder, follow-up and
> sub-availability note drafting — all drafts-only, no send path of any
> kind; caching of all outputs in scores/drafts tables; degradation
> tests: CLI missing, CLI killed mid-run, malformed JSON — nothing
> breaks, features fall back to `none`. Acceptance per PLAN.md §12 M5.
> Update docs/DEMO.md. Do not start M6.

### M6 — Money, scene, people (model: Haiku, `claude-haiku-4-5`; escalate to Sonnet after two failed runs)

> Read CLAUDE.md, PLAN.md, and docs/EXECUTION.md §M6. Implement milestone
> M6 exactly as specified — this is CRUD against the existing schema, no
> new architecture: gigs table + lifecycle (offered→confirmed→played→paid,
> chase-unpaid reminder at played+14d), invoices (numbered, print-ready
> self-contained HTML), income dashboard (monthly, by category, pipeline
> value), rate floor setting + below-floor chips on leads/drafts, scene
> calendar (cadence_json → next-date computation, going flags,
> post-event "met anyone?" prompt linking to people), people log +
> referral chains (person → gig), reminders surfaced in UI. Unit tests
> for next-date computation and invoice numbering. Acceptance per
> PLAN.md §12 M6. Update docs/DEMO.md. Do not start M7.

### M7 — Polish + phone ops (model: Sonnet)

> Read CLAUDE.md, PLAN.md, and docs/EXECUTION.md §M7. Implement milestone
> M7: notification adapter (termux-notification via Termux:API, no-op/log
> fallback on desktop), morning daily digest and Sunday Outreach Sprint
> notifications composed from live data, seasonal playbook activation
> reminders (active_months), metrics page (pitches→responses→bookings by
> category, income by month, source conversion), docs/PHONE.md hardening
> guide (battery optimization exemption, Termux:Boot, wake-lock,
> backups), full docs pass, DEMO.md covering every milestone. Acceptance
> per PLAN.md §12 M7: a fresh-phone install succeeds from docs alone;
> digest arrives as a real Android notification.

## After M7

Stretch items live in PLAN.md §12 "Later / stretch". Each gets planned
into a milestone section here (with a model assignment) before any
session builds it.
