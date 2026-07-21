# CLAUDE.md — conventions for AI coding sessions in this repo

Vamp is a phone-hosted (Termux on Android), local-first copilot for
finding and manufacturing paid musician work in the Oklahoma City metro.
Authoritative docs: `PLAN.md` (what to build and why), `docs/EXECUTION.md`
(the milestone you are building, its session prompt, and which model runs
it). Read both before writing code. Build only the current milestone.

## Hard rules

- **Local-first, phone-first, private:** no cloud services, no telemetry,
  no accounts. Binds to 127.0.0.1 only. PII lives only in SQLite and
  `~/.vamp/` inside Termux private storage.
- **No API keys for AI.** AI goes through the installed `claude` CLI
  (subscription login). Every AI feature must work (degraded) when no
  provider is available — tested behavior, not an aspiration.
- **No scraping or automating Facebook, Instagram, Craigslist, Indeed,
  or LinkedIn. Ever.** The capture flow (Android share-target / paste)
  is the supported path. The page-watcher must refuse blocklisted
  domains and respect robots.txt.
- **No auto-sending, no auto-applying.** Vamp drafts applications,
  pitches, and follow-ups; a human sends every single one. There is no
  code path that transmits a message or application on the user's behalf.
- **No fabricated data.** Seeded venues, contacts, emails, dates, and
  rates must be verified during research or flagged `verified: false`.
  Never invent a contact detail to fill a field.
- **Paid-first is structural.** Unpaid opportunities live on the
  Stepping-stones shelf and never sort above paying work.
- **Filters never silently delete.** Excluded items go to the Excluded
  shelf with a reason chip and one-tap restore.
- **Pure-Python dependencies only.** Termux runs bionic libc; manylinux
  wheels don't install. No pydantic, no lxml, no uvloop, no compiled
  packages — anything compiled comes from `pkg install` or is dropped.
- **Portability:** core runs on desktop Linux too (CI, dev sessions).
  Termux-specific behavior (notifications, wake-lock, services) lives
  behind small adapters with no-op/log fallbacks.
- **Reliability over features:** one failing source/adapter/provider must
  never take down the daemon or other components.

## Tech conventions

- Python 3.11+, stdlib `venv` + `pip`, pinned `requirements.txt`; run
  everything via `make dev` / `make test`.
- Flask + Jinja2 + HTMX; waitress in production; no JS build step, no
  npm for the app. One CSS file. PWA manifest + share-target.
- SQLite in WAL mode via stdlib `sqlite3`; schema changes = new numbered
  SQL file in `migrations/`, applied by the built-in runner. Never edit
  old migrations. Seed data = YAML in `seeds/`, imported idempotently.
- Tests: pytest; adapters/parsers/filters are tested against recorded
  fixtures in `tests/fixtures/` — tests must never perform live HTTP.
- Lint: ruff (format + check) — keep it green in CI.
- Type hints on public functions; dataclasses at API and adapter
  boundaries (no pydantic — see hard rules).
- Logging: structured, to stderr; user-meaningful happenings also go to
  the `events` table.

## Workflow

- Branch: work stays on the designated `claude/…` branch; push with
  `git push -u origin <branch>`.
- Commits: small, imperative, milestone-tagged (`M1: add share-target
  capture endpoint`).
- Each milestone ends with: acceptance criteria met, `make test` green,
  `docs/DEMO.md` updated with how to demo it.
- If reality contradicts `PLAN.md`, fix the plan in the same commit.
