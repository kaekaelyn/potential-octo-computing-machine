# Demo script

Manual-QA script, one section per milestone. Run each section's commands
from the repo root.

## M0 — Skeleton

Desktop Linux:

```sh
make dev
```

Expected output:

```
Vamp serving on http://127.0.0.1:8485  (db: /home/you/.vamp/vamp.db)
```

Open `http://127.0.0.1:8485` in a browser — a "Vamp" dashboard page
loads showing zeroed Sources/Leads/Prospects/Gigs counts, the SQLite db
path, and the app version. `Ctrl+C` to stop.

Verify the health endpoint and schema separately:

```sh
curl -s http://127.0.0.1:8485/healthz
# {"status": "ok"}

sqlite3 ~/.vamp/vamp.db ".tables"
# assets          invoices        playbooks       referrals       scores
# events          kit_tasks       profile         reminders       scene_events
# gigs            leads           prospects       requirements    sources
# patrol_items    people          touches         schema_migrations
```

Run the test suite and linter:

```sh
make test    # pytest — should finish "N passed"
make lint    # ruff format --check, ruff check, pure-Python dep gate
```

Confirm the pure-Python dependency gate actually catches something (it's
otherwise easy to add a compiled package without noticing):

```sh
echo "pydantic==2.9.0" >> requirements.txt
python scripts/check_pure_python_deps.py   # should exit non-zero
git checkout requirements.txt              # revert the probe
```

Termux (see `docs/PHONE.md` for full walkthrough and troubleshooting):

```sh
pkg install -y git python make
git clone <repo-url> vamp && cd vamp
./install.sh
sv status vamp
curl -s http://127.0.0.1:8485/healthz
```

Then open `http://127.0.0.1:8485` in Chrome and "Add to home screen".
Reboot the phone and repeat the `sv status`/`curl` check to confirm the
Termux:Boot autostart path.

## M1 — Capture + leads inbox

Start the app:

```sh
make dev
```

### Paste capture (desktop path)

Open `http://127.0.0.1:8485/capture`, paste a URL or some post text (or
both), and hit Capture. You land on the new lead's detail page. Try a
posting with real JSON-LD (most job boards / ATSs) — title, org,
location, pay, and deadline come back parsed automatically and the lead
is *not* flagged for review.

Now try pasting only text with no working URL, e.g. a caption you'd
copy out of the Facebook app:

```
Piano bar in Bricktown is hiring a keyboardist for Fri/Sat nights,
$200/night plus tips. Message the page!
https://www.facebook.com/groups/okcmusicianscircle/posts/9988776655
```

The fetch to a Facebook URL is expected to fail (or there's no URL to
fetch at all) — Vamp never errors out. Instead you land on the lead's
detail page with a "finish by hand" banner and a form pre-filled from
the shared text, ready to correct.

### Android share-target (phone path)

After `./install.sh` and adding Vamp to the home screen: from Facebook,
Instagram, or any browser, use the OS **Share** sheet on a post → **Vamp**.
Vamp POSTs to `/capture/share`, parses what it can, and opens the new
lead — under 20 seconds from tap to a tracked lead is the target.

### The two-shelf inbox

`http://127.0.0.1:8485/leads` shows **Paying** and **Stepping-stones** as
separate shelves. Capture an unpaid posting (say, an open-mic listing) —
it always lands on Stepping-stones, never Paying, no matter how it
scores; that split is structural, not a sort order.

### Hard filters + the Excluded shelf

Paste in a posting containing "seeking a piano teacher for private
lessons" — it's excluded automatically with a `−teaching` reason chip,
visible at `/leads/excluded`, never in the main inbox. Same for a degree
wall ("Bachelor's degree in Music required", no carve-out) and
pay-to-play ("performers must purchase 20 tickets"). Paste a posting
that requires a degree *with* "...or equivalent experience" language —
it is **not** excluded; the carve-out opens the wall. Tap **Restore** on
any excluded lead to bring it back to the inbox with one tap.

### Dedupe

Capture the same posting twice (same URL, or same title/org/date) — the
second capture redirects to the *same* lead instead of creating a
duplicate.

### Patrol checklist

`http://127.0.0.1:8485/patrol` — add a Facebook group/page worth a daily
skim, tap **Checked** once you've looked today (highlights green), edit
or delete items. This is the ToS-compliant answer to Facebook: Vamp
never automates it, just tracks whether you did it.

### Tests

```sh
make test    # 62+ tests: filters, dedupe, capture parser, all routes
make lint
```

Fixture-based coverage lives in `tests/fixtures/`: real-shaped posting
texts proving the teaching filter, the degree-wall filter (including the
"or equivalent" carve-out), the pay-to-play filter, and JSON-LD/
OpenGraph/heuristic/share-text parsing — none of it touches the network.

## M2 — Feeds + watchers

Start the app:

```sh
make dev
```

### Sources admin page

Open `http://127.0.0.1:8485/sources`. Adzuna and USAJOBS are seeded
automatically on first run, enabled by default, showing "last fetch:
never" and "last success: never". Tap **Disable**/**Enable** to toggle a
source; the flip is instant and persists (no restart needed).

### Configuring API keys

Adzuna and USAJOBS need free API keys before they'll actually fetch
anything. Add them to `~/.vamp/env` (created for you on first run, mode
600):

```
ADZUNA_APP_ID=your-app-id
ADZUNA_APP_KEY=your-app-key
USAJOBS_API_KEY=your-api-key
USAJOBS_EMAIL=you@example.com
```

Without keys, a poll still runs on schedule but records
`last_error: "Adzuna not configured: ..."` (or the USAJOBS equivalent) on
`/sources` instead of silently doing nothing — the failure is visible, not
swallowed.

### RSS + page watcher

From `/sources`, add an RSS feed (name + feed URL) — polled every few
hours by default. Add a page watcher (name + URL + mode + interval, min
24h): pick **Whole-page diff** to watch an entire page for any change, or
**CSS selector** (e.g. `#opportunities`) to watch just one section. Try
adding `https://www.facebook.com/groups/anything` as a page watcher — it's
refused immediately with an explanation; capture (share-to-Vamp) is the
only supported path for that domain, same for instagram/craigslist/indeed/
linkedin.

The first poll of a new page watcher only seeds its baseline (no lead —
nothing to alert on yet); the next poll that finds different content
creates a lead flagged "finish by hand" (`needs_review`) with the changed
text, so you decide what it means.

### Scheduling: APScheduler + catch-up-on-open

Each enabled source gets its own APScheduler job at its configured
interval, with jitter (so sources don't all fire in lockstep) and a
misfire grace equal to the interval (a process that was asleep through a
missed run fires once on wake, not once per missed interval).
Independently, **every page load** checks whether any source is overdue
and — if so — kicks off a catch-up poll in the background. Demo it:

```sh
sqlite3 ~/.vamp/vamp.db "UPDATE sources SET last_fetch_at = datetime('now', '-1 day') WHERE kind = 'adzuna';"
```

Reload any page in the browser, then check `/sources` a few seconds
later — Adzuna's `last_fetch_at` (and `last_error`, if no key is
configured yet) has updated without restarting the process.

### Reliability: one bad source can't take down the others

Every fetch is wrapped per-source; a raising adapter is caught, logged to
that source's `last_error`, and recorded as an `events` row — the next
source in the same run still fetches normally. `make test` includes a
dedicated isolation test (`tests/test_source_runner.py::
test_one_raising_source_does_not_affect_others`) proving this directly.

### New leads flow through the M1 filters automatically

Anything an adapter returns goes through the same dedupe + hard-filter
pipeline as capture: a fetched posting matching the teaching/degree-wall/
pay-to-play patterns lands straight on the Excluded shelf with its reason
chip, and duplicates (by URL or by org/title/date) never create a second
lead — same as pasting or sharing one by hand.

### Tests

```sh
make test    # 116+ tests: adapters (fixture-only, no live HTTP), runner
             # isolation, scheduler reconciliation, catch-up-on-open, /sources
make lint
```
