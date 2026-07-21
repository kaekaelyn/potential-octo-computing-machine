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
