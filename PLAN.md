# Vamp — Master Plan

A phone-hosted, local-first copilot for building a working musician's career
in the Oklahoma City metro. Built for Kaelyn: pianist/keyboardist (own rig,
will play real pianos), singer-songwriter, free-improviser who can vamp
indefinitely — hence the name ("vamp till ready").

Wingman (the sibling project) automates a *job search*: find postings, apply
fast. A musician's problem is different: **most paying music work in a city
like OKC is never posted anywhere.** It's booked through relationships,
cold pitches, showing up, and being the person a venue already knows.
So Vamp is half aggregator, half **outbound engine**: it hunts the postings
that do exist, and it systematically manufactures the opportunities that
don't.

---

## 1. Goals and non-goals

### Goals

1. **Paid work is the point.** Every feature bends toward money arriving.
   Unpaid things (open mics, competitions, showcases) are in scope only as
   *stepping stones* and are always ranked below paid work, never mixed in.
2. **Catch everything that IS posted.** Gig listings, event bookings, and
   salaried musician jobs (church positions, accompanist posts, retirement
   communities, military bands, hotels) from every legitimately reachable
   source, deduplicated, filtered, ranked.
3. **Manufacture what isn't posted.** A prospects engine: a researched,
   verified database of OKC-metro places that *should* have live piano and
   the people who book them, with a pipeline (identify → research → pitch →
   follow up → booked → recurring) and AI-drafted personalized pitches.
   Kaelyn sends every message herself; Vamp does everything up to "press
   send."
4. **Answer "what do I need to apply?" instantly.** Every opportunity is
   decomposed into a requirements checklist (live video, CV, repertoire
   list, references, audition…) matched against the asset vault, so each
   card shows READY or exactly what's missing — and an "unlock report"
   shows which single missing asset opens the most doors.
5. **Build the kit.** Starting from scratch on materials is a supported
   state: a guided kit-builder milestone walks through bio, headshots,
   live videos, demos, repertoire list, tech rider, rate card, and EPK,
   with AI drafting help.
6. **Filters that respect her time.** One-toggle exclusion of teaching
   jobs; automatic exclusion of degree-required postings that offer no
   "or equivalent experience" language. Excluded items go to a reviewable
   shelf, never silently deleted.
7. **Phone-first, phone-hosted.** The entire app runs on Kaelyn's Android
   phone under Termux. The phone is server and client. No other hardware.
8. **AI as amplifier, never dependency.** Claude CLI via subscription
   (no API keys), with every feature functional (degraded) without it.

### Non-goals (deliberate)

- **No auto-applying, no auto-sending. Ever.** Vamp drafts applications,
  pitches, and follow-ups; a human sends 100% of them. (This also deletes
  Wingman's hardest milestone — no Playwright, no fillers.)
- **No scraping or automating Facebook, Instagram, Craigslist, Indeed,
  LinkedIn, or any ToS-hostile platform.** OKC gig chatter lives on
  Facebook; the answer is a *fast capture flow* (Android share-target:
  share any post/page/listing to Vamp and it becomes a parsed lead) plus
  a daily patrol checklist of groups worth skimming by hand.
- **No fabricated data.** Venue names, contacts, emails, and event dates in
  seed datasets must be verified during research sessions or explicitly
  flagged `verified: false` ("confirm before pitching"). An AI-hallucinated
  booking email is worse than no email.
- **No cloud service, no accounts, no telemetry.** Local-first forever.

---

## 2. Architecture overview

```
┌────────────────────────────────────────────────────────────┐
│ Android phone — Termux                                     │
│                                                            │
│  Vamp daemon (single Python process, termux-services/runit)│
│   ┌──────────┐  ┌─────────┐  ┌────────┐  ┌─────────────┐   │
│   │ Scheduler │→│ Source   │→│ Dedupe │→│ Filter+Score │   │
│   │(APSched. +│ │ adapters │ │ + norm │ │ (heuristic   │   │
│   │ catch-up) │ └─────────┘ └────────┘ │  and/or AI)  │    │
│   └──────────┘                          └──────┬──────┘    │
│   ┌──────────────── SQLite (WAL) ──────────────▼────────┐  │
│   │ leads · requirements · assets · prospects · touches │  │
│   │ people · scene_events · gigs · invoices · reminders │  │
│   └─────────────────────────────────────────────────────┘  │
│                                                            │
│   Flask ──→ Web UI (Jinja2 + HTMX, PWA + share-target)     │
│   AI: subprocess `claude -p` (Node on Termux) │ heuristics │
│   Notify: termux-notification (Termux:API) — fully local   │
│                                                            │
│  Chrome/any browser → http://127.0.0.1:8485  (home-screen  │
│  PWA; "Share → Vamp" from any app = capture)               │
└────────────────────────────────────────────────────────────┘
```

### Stack — chosen for Termux reliability

Termux runs Android's bionic libc, so **manylinux wheels do not install**.
Compiled Python packages (pydantic-core, uvloop, lxml, orjson…) are a
recurring tar pit there. Rule: **pure-Python dependencies only** in the
app; anything compiled must come from `pkg install` or be dropped.
This is why Vamp deliberately diverges from Wingman's FastAPI/uv stack:

| Concern | Choice | Why |
| --- | --- | --- |
| Language | Python 3.11+ (Termux `pkg install python`) | current on Termux |
| Env/packaging | stdlib `venv` + `pip`, pinned `requirements.txt` | uv/bionic is unreliable; venv+pip always works |
| Web/API | Flask + Jinja2 (pure Python) | FastAPI drags in pydantic-core (Rust) — no bionic wheel |
| WSGI server | waitress (pure Python) | production-ish, no compiler |
| Validation | stdlib dataclasses + small validators | no pydantic on bionic |
| DB | SQLite (WAL), stdlib `sqlite3` | zero admin, one-file backup |
| Migrations | numbered SQL files + tiny runner | Wingman pattern, proven |
| Scheduler | APScheduler (pure Python) + catch-up-on-open | see "phone realities" |
| HTTP client | httpx (pure-Python mode) | timeouts, retries |
| Parsing | feedparser, beautifulsoup4 w/ `html.parser`, stdlib json | all pure Python |
| UI | Jinja2 + HTMX + one CSS file | no node toolchain for the app itself |
| AI | subprocess to `claude -p --output-format json` | Node via `pkg install nodejs-lts`; subscription login, no API key |
| Push | `termux-notification` (Termux:API) | real Android notifications, zero cloud |
| Service | termux-services (runit) + Termux:Boot | starts on boot, restarts on crash |
| Tests | pytest, recorded fixtures | never live HTTP in tests |
| Lint | ruff in CI (x86 runners); optional `pkg install ruff` on device | keep green |

**Portability rule:** the core app must also run on plain desktop Linux
(that's where CI and coding sessions run). All Termux-specific behavior
(service scripts, `termux-notification`, wake-lock) is isolated behind
small adapters with a no-op/log fallback, so `make dev` works anywhere.

### Phone realities (and how Vamp survives them)

Android kills background processes. Mitigations, in order:

1. `termux-wake-lock` held by the service; install docs walk through
   exempting Termux from battery optimization.
2. Termux:Boot starts the service on phone restart.
3. **Catch-up-on-open:** every UI page load checks source staleness and
   triggers an immediate poll if any source is overdue. Even if Android
   killed everything overnight, opening the app self-heals within seconds.
4. Missed-schedule tolerance in APScheduler (misfire grace) so a slept
   process fires once on wake, not 40 times.

Install story: install Termux + Termux:API + Termux:Boot (F-Droid), then
`pkg install git python make termux-api termux-services && git clone … &&
cd vamp && ./install.sh` → prints `http://127.0.0.1:8485` → open in
Chrome → "Add to home screen."

---

## 3. Intake: where opportunities come from

Three intake channels, all landing in one normalized `leads` table.

### Tier A — feeds and APIs (polled automatically)

| Source | Access | What it catches |
| --- | --- | --- |
| Adzuna | free API key | salaried/hourly musician, pianist, accompanist, music-director jobs, OKC + radius |
| USAJOBS | free API key | **military bands** — Army/Air Force band keyboardist posts: salaried, benefits, real auditions |
| Generic RSS | any feed URL | church-job boards, arts orgs, anything with a feed — the escape hatch |
| Page watcher | polite HTML diff/CSS-selector watcher | pages with no feed: arts-council opportunity pages, venue "auditions" pages, festival application pages. Respects robots.txt; per-page interval ≥ daily; capture-only platforms are refused by domain blocklist |
| Curated deadline calendar | seed data in repo | annual competitions/showcases (songwriting competitions, festival applications, contest cycles) that recur predictably — surfaced as leads when their windows approach |

### Tier B — capture (the Facebook answer)

The PWA registers as an **Android share target**. From the Facebook app,
Instagram, Craigslist, a browser — Share → Vamp. Vamp fetches what it's
allowed to, parses JSON-LD/OpenGraph/heuristics, and creates a lead; when
a platform blocks fetching (FB often will), the share text itself is
parsed and the lead is created with a "finish by hand" form pre-filled.
Target: **under 20 seconds from seeing a post to a tracked lead.**
Plus a paste-a-URL/paste-text box in the UI for desktop use.

A **daily patrol checklist** (seeded, editable) lists the FB groups and
pages worth a 5-minute manual skim (OKC musicians' groups, venue pages,
church-network pages), with per-item "checked today" ticks — turning the
ToS-compliant manual path into a fast habit instead of a vague guilt.

### Tier C — prospects (opportunities that don't exist yet)

Covered in §6 — the outbound engine. Prospects are a separate table from
leads; a prospect that responds becomes a gig without ever being a
"posting."

Dedupe across everything: normalized (org, title, event-date/location)
fuzzy hash + canonical URL hash, Wingman-style.

---

## 4. Filters and scoring

### Hard filters (toggleable, default ON, never silent)

- **Teaching filter:** excludes lessons/instructor/faculty/adjunct/tutor
  postings. Kaelyn performs; she doesn't want teaching offers in the feed.
- **Degree filter:** excludes postings that require a music degree with
  *no* "or equivalent experience/training" language. Heuristic regex
  first; AI second-opinion pass when available (this is exactly the kind
  of nuance-reading a cheap AI call is good at).
- **Pay-to-play filter:** flags "exposure" scams — required ticket sales /
  "bring 20 people" / pay-to-perform showcases. Flagged hard, excluded by
  default.

Everything excluded lands on the **Excluded shelf** with the reason chip
(`−teaching`, `−degree-wall`, `−pay-to-play`), one tap to restore. False
positives are recoverable; trust in the filter is the feature.

### Scoring (heuristic always; AI on top when available)

0–100 with "why" chips, ranked feed. Signals: pay amount and certainty
(`+$200 flat` beats `+tips`), distance from OKC (Edmond/Moore/Yukon/
Norman fine, decay beyond ~45 min), fit tags (piano/keys/vocals/
improv/accompanist), recency, deadline pressure, venue-hires-from-here
history (open mics known to feed bookings score above random ones).

**Paid-first is structural, not just a weight:** the feed is two shelves —
**Paying** and **Stepping stones** — and unpaid never sorts into the
first shelf. A stepping stone earns its place only via strategic value:
cash-prize competitions, showcases with real bookers, open mics at venues
that hire, networking events with named people worth meeting.

---

## 5. Requirements decomposition, asset vault, kit builder

### Requirements parser
Every lead's text is decomposed into a checklist of concrete asks:
`live video` · `audio demo` · `CV/resume` · `bio` · `repertoire list` ·
`references` · `headshot` · `EPK/website link` · `in-person audition` ·
`cover letter` · `other (verbatim)`. Heuristic keyword/pattern pass
always; AI extraction pass (cached) when available. Fixture-tested
against a corpus of real posting texts.

### Asset vault
The things those checklists ask for, stored/linked once, tagged, dated:
bios at 50/150/300 words, headshots, live videos (link or file), audio
demos, repertoire list (tagged by occasion: wedding/cocktail/worship/
jazz/originals/improv), CV, references, tech rider + stage plot for the
keyboard rig, rate card, EPK.

Each lead card then shows **READY** or **Missing: live video** at a
glance. The **Unlock report** answers "what do I build next?": *"One
3-minute live video unlocks 7 of your 11 open opportunities."*

### Kit builder (because we're starting from scratch)
A guided, ordered checklist that is itself a first-class milestone:
questionnaire → AI-drafted bios in her voice → shot list for headshots →
a minimal-gear plan for three live videos (solo piano improv · voice+
piano original · covers sampler — one phone, one good take each) →
repertoire list builder → rate card with researched OKC market ranges →
**EPK export**: a static one-page HTML file generated from the vault that
she can send as an attachment, print to PDF, or host anywhere (hosting is
her choice; Vamp never publishes anything itself).

---

## 6. The prospects engine (the edge)

This is Vamp's equivalent of Wingman's apply engine: the thing that makes
it more than a feed reader. Most OKC piano work is unposted; the engine
makes cold outreach systematic instead of scary.

### Prospect database
Seeded three ways, unified in one pipeline:
- **Curated seed data** (researched and verified during the build):
  OKC-metro venues by category — piano bars, hotel lobbies/bars,
  steakhouses and upscale restaurants, wineries/breweries, coffee
  shops, listening rooms, churches by size/denomination-friendliness,
  retirement and assisted-living communities, hospitals with arts
  programs, wedding venues and planners, funeral homes, galleries,
  museums, country clubs, theaters, dance studios and university dance
  departments, improv/comedy theaters, yoga studios.
- **OpenStreetMap Overpass API import:** free, legit bulk discovery of
  category × geography (all `amenity=restaurant` with `cuisine=steak` in
  the metro, all senior-living facilities, etc.) as `verified: false`
  raw material.
- **Manual add** — met someone, saw a place with a dusty grand piano.

Each prospect: category, area, contacts, best channel, `has_piano`,
`verified`, notes, and an **angle** — the one-line reason *this* pitch
lands ("has a lobby grand nobody plays", "does jazz brunch with no
live music", "books singer-songwriters on Thursdays").

### Pipeline and cadence
`identified → researched → pitch drafted → contacted → follow-up 1 →
follow-up 2 → in conversation → booked → recurring | dead`. Silence is
not a no: the cadence engine schedules the follow-ups (+7d, +21d) and
the weekly **Outreach Sprint** notification packages them: *"This week:
5 pitches drafted and ready, 3 follow-ups due. Open Vamp."* Kaelyn
reviews, personalizes, and sends each one herself — always.

### Playbooks (the creative part, shipped as content + seed data)

Strategy playbooks are first-class app content: each is a short
written strategy plus the pre-seeded prospects/scene-events to execute it.

1. **The Free-Improv Arbitrage.** Indefinite improvisation is a rare,
   monetizable skill most pianists can't offer. Markets that pay for
   exactly it: **dance-class accompaniment** (ballet/modern programs and
   studios need improvising accompanists — steady hourly institutional
   work, chronically undersupplied); **silent-film and museum event
   scoring**; **yoga/meditation/sound-bath live music**; **gallery
   openings and art walks** (ambient improv is the perfect fit);
   **theater underscoring and improv-comedy accompaniment**. These become
   seeded prospect categories with the pitch angle pre-written.
2. **The Retirement Circuit.** Activity directors book entertainment
   monthly with real budgets and low friction. Land 8–10 communities on
   a rotating monthly route = a steady income floor that funds everything
   else. Vamp treats the circuit as a trackable route with per-facility
   cadence.
3. **The Dormant Piano Tour.** Venues that own a piano nobody plays are
   pre-qualified leads — the capital cost is already sunk. Seed list of
   metro venues with pianos; pitch angle: "your piano could be earning."
4. **The Sub List.** Churches and bands constantly need last-minute subs.
   Vamp maintains a one-page sub sheet (from the vault) and a contact
   list of worship leaders and music directors; one tap drafts an
   "available this Sunday" note to send. Sub work is how you become the
   next hire.
5. **The Planner Play.** For weddings/private events, pitch the twenty
   planners, not the two thousand couples. Wedding planners, corporate
   event planners, and venue coordinators are repeat referrers; Vamp
   tracks them as `people`, not one-off prospects.
6. **Seasonal campaigns.** Booking runs months ahead of the calendar:
   September = pitch holiday corporate parties; January = wedding-planner
   outreach for the season; pre-Christmas/Easter = church sub
   availability blitz. Playbooks activate as reminders on schedule.
7. **The Scene Ledger.** Showing up is a strategy: First Friday art
   walks, monthly plaza events, open-mic and songwriter-round circuits,
   festivals and their application windows, listening rooms, university
   music-school orbit. The scene calendar (§7) tracks where to be; the
   people log tracks who was met; referral tracking shows which
   relationships actually produce gigs.

All seed data ships as editable YAML in the repo, imported by migration,
with `verified` flags and a "confirm before pitching" banner on anything
unverified.

---

## 7. Scene calendar, people, and the daily loop

- **Scene calendar:** recurring events (open mics, jams, art walks,
  songwriter rounds, mixers, festival windows) with next-date computation,
  "going" flags, and post-event prompt: *"Meet anyone?"* → one-tap add to
  people log.
- **People log:** lightweight CRM — name, role (booker/worship leader/
  planner/musician), where met, notes, and referral chain (which contact
  led to which gig). Referrals are the metric that matters.
- **Daily digest** (`termux-notification`, morning): *"2 new paying leads
  (1 READY), 3 follow-ups due, open mic tonight at [venue]."* Tap → PWA.
- **Weekly Outreach Sprint** (Sunday evening): the drafted-pitch bundle.
- **Metrics:** pitches sent → responses → bookings by category; income by
  month/venue-type; which sources and playbooks actually convert.

---

## 8. Money (being paid is the goal)

- **Gigs table:** every booked engagement — date, venue/prospect link,
  agreed pay, actual pay, expenses, mileage, notes. States: offered →
  confirmed → played → **paid** (with a "chase unpaid" reminder if a gig
  stays played-not-paid past 14 days).
- **Invoices:** numbered, generated as print-ready HTML → share/print to
  PDF from the phone. No payment processing — just the paper trail.
- **Rate card + floor:** researched OKC-market rate ranges by gig type in
  seed data (verified during build); a personal floor setting; leads and
  drafts below floor get a `−below-floor` chip unless flagged strategic.
- **Income dashboard:** monthly totals, by category, pipeline value
  (confirmed-future gigs), year view.

---

## 9. AI integration (subscription CLI, optional, phone-resident)

Same contract as Wingman, adapted to Termux:

| Provider | Mechanism | Notes |
| --- | --- | --- |
| `claude` | subprocess `claude -p --output-format json` | Node via `pkg install nodejs-lts`, `npm i -g @anthropic-ai/claude-code`, `claude login` once with the household subscription. Known to run on Termux/ARM64; treated as *fragile by policy* |
| `none` | heuristics + templates | always present, always tested |

(`codex` CLI support is stretch — its Termux story is worse; the
abstraction leaves room for it.)

Rules: graceful degradation is tested behavior — kill the CLI mid-run,
nothing breaks, features fall back. Calls are queued and batched
(nightly scoring run, weekly pitch-draft run) to respect subscription
limits and phone battery. All outputs cached in SQLite; nothing is
scored twice. Health panel shows "Claude: logged in ✓ / missing —
here's how to fix it on Termux."

AI features, priority order:
1. Lead scoring rationale + red flags (ghost gigs, pay-to-play,
   degree-wall second opinions)
2. Requirement extraction from posting text
3. Pitch drafting: personalized per-prospect from vault + angle + her
   voice sample (drafts only; she sends)
4. Bio/EPK copy drafting in the kit builder
5. Follow-up and "available this Sunday" note drafting
6. Weekly strategy digest: what converted, what to try next week

---

## 10. Data model (SQLite, one file)

```
sources(id, kind, name, config_json, enabled, last_fetch_at, last_error,
        interval_seconds, last_success_at)  -- interval/last_success added M2, migration 0003
source_state(source_id, content_hash, updated_at)  -- adapter poll state (M2); page-watcher's diff hash
leads(id, source_id, kind,           -- gig|job|competition|open_mic|showcase|other
      dedupe_hash,                   -- fuzzy (org, title, event_date) key
      url_hash,                      -- canonical-URL key (M1, migration 0002)
      url, title, org, location, pay_min, pay_max,
      pay_kind,                      -- flat|hourly|salary|tips|unpaid|unknown
      deadline, event_date, description, posted_at, first_seen_at,
      state,                         -- inbox|interested|preparing|applied|booked|passed|excluded
      excluded_reason,               -- comma-separated reason codes
      needs_review,                  -- capture fetch failed; finish-by-hand form (M1)
      raw_json)
requirements(id, lead_id, kind, detail, satisfied_asset_id)
assets(id, kind, name, path_or_url, tags, updated_at, ready)
kit_tasks(id, ord, title, detail, asset_kind, state)
prospects(id, name, category, area, address, phone, email, website,
          socials_json, has_piano, angle, status, source, verified,
          notes, last_touch_at, next_touch_at)
touches(id, prospect_id, ts, channel, summary, outcome)
people(id, name, role, org, met_at, contact_json, notes)
referrals(id, person_id, gig_id)
scene_events(id, name, cadence_json, venue, area, url, kind, notes, going)
patrol_items(id, name, url, notes, last_checked_at)
gigs(id, prospect_id, lead_id, date, venue, pay_agreed, pay_received,
     expenses, mileage, state, notes)
invoices(id, gig_id, number, issued_at, paid_at, amount, html_path)
playbooks(id, slug, title, body_md, active_months)
scores(lead_id, scorer, score, rationale_json, scored_at)
reminders(id, ref_kind, ref_id, due_at, message, done)
profile(key, value)
events(id, ts, kind, payload_json)
```

Backup: `vamp backup` tarballs DB + assets to Android shared storage
(`termux-setup-storage`); docs recommend pointing Syncthing or a cloud
drive at the backup folder — user's choice, app stays offline.

---

## 11. Security and privacy

- Binds to `127.0.0.1` only. The server and the browser are the same
  phone; nothing is ever exposed to any network. (If she later moves it
  to a box, the Wingman PIN-gate pattern is the blessed path.)
- PII (contacts, rate card, people log) lives only in SQLite +
  `~/.vamp/` inside Termux's private storage; backups to shared storage
  are explicit user actions.
- No credentials for any platform are ever stored. Capture works on
  content she shares to the app; nothing logs in as her.
- Secrets (Adzuna/USAJOBS keys) in `~/.vamp/env`, mode 600.

---

## 12. Milestones

Each milestone = one scoped coding session with demoable output and
acceptance criteria; session prompts and **model assignments** live in
`docs/EXECUTION.md`. Ordering front-loads the daily-usable core: capture
+ filters land before feeds, because share-from-Facebook is the #1 intake
on day one.

### M0 — Skeleton, Termux-first (small) — Sonnet
Repo scaffold: venv+pip project, Flask app + health page at
`http://127.0.0.1:8485`, SQLite schema (§10) + migration runner, config
loading, `install.sh` (Termux-aware, desktop-dev fallback),
termux-services scripts + Termux:Boot hook, wake-lock, Makefile
(`dev`/`test`/`lint`), pytest + ruff, GitHub Actions CI.
**Accept:** on desktop `make dev` serves the UI and `make test` is green
in CI; on the phone, `./install.sh` + `sv-enable vamp` survives a Termux
restart.

### M1 — Capture + leads inbox (medium) — Sonnet
PWA manifest + service worker + **Android share-target**, paste-URL/
paste-text capture, JSON-LD/OpenGraph/heuristic parsing with graceful
"finish by hand" pre-filled form, `leads` states, dedupe, teaching/
degree/pay-to-play filters with Excluded shelf and reason chips,
Paying vs Stepping-stones shelves, patrol checklist page.
**Accept:** share a Facebook post → parsed lead in <20s; filter fixtures
prove teaching/degree exclusions incl. "or equivalent" carve-out.
**← Daily-usable from this day.**

### M2 — Feeds + watchers (medium) — Sonnet
Source adapter protocol, Adzuna + USAJOBS adapters (musician/pianist/
accompanist queries, OKC radius), generic RSS, polite page-watcher
(robots.txt, domain blocklist for capture-only platforms), APScheduler +
catch-up-on-open, misfire grace, sources admin page, events log.
**Accept:** real salaried leads flow in on the phone; a raising adapter
never affects others (tested); killing/restarting the process self-heals.

### M3 — Requirements + vault + kit builder (medium) — Sonnet
Requirements parser (heuristic, fixture corpus of real postings), asset
vault CRUD, READY/Missing matching on lead cards, Unlock report, kit
builder guided checklist, repertoire list builder, EPK static-HTML
export, backup command.
**Accept:** a captured posting shows a correct requirements checklist;
the unlock report identifies the highest-leverage missing asset; EPK
exports as a self-contained file.

### M4 — Prospects engine + OKC seed data (large) — **Opus, research-heavy**
Prospect pipeline (states, angles, cadence engine, follow-up reminders,
touches log), Overpass importer, and the **researched seed datasets**:
metro venues by category, dance/theater/gallery/yoga improv markets,
retirement communities, churches, planners, scene calendar, patrol list,
competition deadline calendar, rate ranges, the seven playbooks as
content. Every seeded fact web-verified or flagged `verified: false`.
**Accept:** pipeline works end-to-end on a real prospect; seed data
passes a verification spot-check; zero fabricated contacts.

### M5 — AI layer (medium) — Sonnet
Provider abstraction (`claude`/`none`), Termux Node install docs +
health panel, queued batch scoring, requirement-extraction pass,
pitch/bio/follow-up drafting, caching, degradation tests (kill CLI
mid-run → nothing breaks).
**Accept:** with `claude` logged in, new leads get scores/rationales and
one-tap pitch drafts; logged out, everything still works.

### M6 — Money, follow-ups, scene, people (medium, CRUD-heavy) — Haiku
Gigs + invoices (print-ready HTML), income dashboard, chase-unpaid
reminders, rate floor chips, scene calendar with next-date computation
and "met anyone?" flow, people log + referral chains.
**Accept:** full loop on a fake gig: booked → played → invoiced → paid;
scene event fires a reminder; referral chain renders.

### M7 — Polish + phone ops (small-medium) — Sonnet
Daily digest + Outreach Sprint notifications via termux-notification,
seasonal playbook activation reminders, metrics page, battery/boot
hardening docs, `docs/PHONE.md`, docs pass, DEMO.md complete.
**Accept:** morning digest arrives as a real Android notification;
fresh-phone install from docs alone succeeds.

### Later / stretch
- Ticketmaster Discovery API import (venues that book live music →
  prospects), codex CLI provider, house-concert circuit playbook,
  grant-deadline calendar for individual artists, weekly AI "state of
  the hustle" summary, desktop capture bookmarklet.

---

## 13. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Android kills the daemon | wake-lock + Boot + catch-up-on-open; the app self-heals on open, and capture (the #1 intake) needs no background process at all |
| Compiled-wheel breakage on Termux | pure-Python dependency rule enforced in CI (a check that fails on known-compiled packages) |
| Claude CLI fragile on Termux | fragile-by-policy: batch queue tolerates absence; heuristics always shipped; health panel explains fixes |
| Facebook blocks URL fetch on capture | share-text parsing + pre-filled manual form is the designed path, not a failure mode |
| Seed data rot (venues close, staff turn over) | `verified` dates, "confirm before pitching" banners, one-tap mark-dead; research session verifies at build time |
| Outreach feels spammy / hurts local reputation | human sends everything; per-prospect cooldowns; drafts personalized by angle, never blast templates; small-city rule in playbook content: every message is one she'd stand behind at an open mic |
| Unpaid work creep | structural Paying/Stepping-stones split; pay-to-play filter; below-floor chips; income dashboard keeps the score honest |
| She stops opening the app | M1 makes it useful day one; daily digest + Outreach Sprint notifications; metrics show money, the only motivator that matters |
