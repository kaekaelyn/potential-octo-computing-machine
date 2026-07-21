# Running Vamp on the phone (Termux)

Vamp is designed to run entirely on Android under Termux — the phone is
both server and client. This doc is the installer's companion: what
`install.sh` does on Termux, why, and how to verify/troubleshoot it on a
real device.

> **Status:** the Termux path below is **code-reviewed, not yet verified
> on a physical device** (M0 acceptance criteria per `docs/EXECUTION.md`).
> The desktop-Linux path (`install.sh` with no `$TERMUX_VERSION`) *is*
> verified — it's how this milestone was built and tested. If something
> here doesn't match reality on-device, fix this doc and `install.sh` in
> the same commit (CLAUDE.md: "if reality contradicts the plan, fix the
> plan").

## One-time device setup

1. Install [Termux](https://termux.dev/) **from F-Droid**, not the Play
   Store build (which is unmaintained and can't self-update packages).
2. Install **Termux:API** and **Termux:Boot**, also from F-Droid — same
   signing key family as Termux itself, required for `termux-*` commands
   (including `termux-notification`, the morning digest/Outreach Sprint's
   delivery mechanism — PLAN.md §7/§9) and boot-time autostart respectively.
3. Open Termux:Boot once after installing it so Android registers it as
   a boot-completed receiver.
4. In Android Settings → Apps → Termux → Battery, exempt Termux from
   battery optimization ("Unrestricted" / "Don't optimize"). Without
   this, Android will kill the background service regardless of
   wake-locks or boot scripts.
5. On Android 13+, the first time Termux:API tries to post a notification
   it triggers the OS's runtime notification-permission prompt — grant it.
   If you miss the prompt, grant it by hand: Android Settings → Apps →
   Termux:API → Notifications → Allow. Without this, `termux-notification`
   reports success but nothing ever appears in the tray.

## Install

```sh
pkg update -y
pkg install -y git python make
termux-setup-storage   # only needed later, for `vamp backup`
git clone <repo-url> vamp
cd vamp
./install.sh
```

## What `install.sh` does on Termux

1. Creates `.venv` in the repo and installs `requirements.txt` (pure
   Python only — see CLAUDE.md "Hard rules" — so this step never needs a
   compiler).
2. Initializes `~/.vamp/env` (config, mode 600) and the SQLite database
   at `~/.vamp/vamp.db`, applying migrations.
3. Installs `termux-services` and `termux-api` (via `pkg`) if the
   `sv-enable`/`termux-wake-lock` commands aren't already on `PATH`.
4. Writes a [runit](http://smarden.org/runit/) service definition to
   `$PREFIX/etc/sv/vamp/run` (rendered from
   `termux/service-run.template`) that: `cd`s into the repo, takes a
   `termux-wake-lock`, and `exec`s `.venv/bin/python -m vamp.wsgi` —
   logging to `~/.vamp/service.log`. `exec` (not a backgrounded
   subprocess) is required: runit supervises the service's own PID, and
   a script that daemonizes/forks breaks that contract.
5. Runs `sv-enable vamp`, which (per termux-services' Void-Linux-style
   layout) symlinks `$PREFIX/etc/sv/vamp` into `$PREFIX/var/service`,
   the directory `runsvdir` watches — this both starts the service now
   and marks it to persist across `sv` restarts. Then `sv up vamp`.
6. Writes `~/.termux/boot/start-vamp.sh` (rendered from
   `termux/boot-start.template`), which Termux:Boot runs on every device
   boot. Boot scripts don't run as a login shell, so
   `termux-services`' own supervisor (`runsvdir`) may not be up yet; the
   script starts it if it isn't running, waits briefly, then
   `sv-enable`/`sv up`s the vamp service. It also takes its own
   wake-lock, in case the app was killed and this is a cold boot.

## Verifying it worked

```sh
sv status vamp          # should print "run:" and a PID
curl -s http://127.0.0.1:8485/healthz   # {"status": "ok"}
tail -f ~/.vamp/service.log
```

Then open `http://127.0.0.1:8485` in Chrome and "Add to home screen" for
a PWA-like launch icon.

To confirm the boot path survives a restart: reboot the phone, wait ~30
seconds after unlock, then repeat the `sv status` / `curl` check above
without opening Termux manually.

## Notifications

The morning digest (8am) and the Sunday Outreach Sprint (6pm) fire as real
Android notifications via `termux-notification` (PLAN.md §7/§9/§12 M7).
`install.sh` already installs the `termux-api` package (the CLI half); the
**Termux:API app** from F-Droid (the Android half) is the one-time device
setup step above, and the notification permission on Android 13+ is the
other. Verify the whole path end to end:

```sh
termux-notification --title "Vamp" --content "test notification"
```

A notification should appear in the tray immediately. If it doesn't:

- `command -v termux-notification` — empty means the `termux-api` package
  isn't installed (`pkg install -y termux-api`).
- Confirm the Termux:API **app** (not just the package) is installed from
  F-Droid — the CLI shells out to it over a Unix socket; the package alone
  does nothing.
- Check the notification permission (Android 13+): Settings → Apps →
  Termux:API → Notifications → Allow.

Once that works, use `/notify` in the app to check status and fire either
notification on demand (`Send digest now` / `Send Outreach Sprint now`) —
useful for confirming the whole pipeline (live data → composed text →
`termux-notification`) without waiting for the scheduled hour. Without
Termux:API (desktop, or before it's installed on the phone), the same
message is logged to `~/.vamp/service.log` instead of failing — CLAUDE.md's
portability rule that core behavior always has a non-Termux fallback.

## Troubleshooting

- **`sv-enable: command not found` right after install** — the
  `termux-services` package adds shell integration that a running shell
  won't pick up until it restarts. Close and reopen Termux, then rerun
  `sv-enable vamp && sv up vamp`.
- **Service enabled but not running** — check
  `~/.vamp/service.log` and `cat $PREFIX/etc/sv/vamp/run` for a stale
  path (e.g. the repo was moved after install; rerun `./install.sh` to
  regenerate the run script with the current path).
- **Nothing starts after a reboot** — confirm Termux:Boot is installed
  *and was opened at least once*, and that Termux is exempt from battery
  optimization (Android can silently prevent boot receivers from firing
  otherwise). Check `~/.vamp/runsvdir.log` for evidence the boot script
  ran at all.
- **Killed during heavy background app usage** — this is the phone
  realities problem PLAN.md §2 describes; `termux-wake-lock` plus
  catch-up-on-open (from M2 onward) are the mitigations. Opening the app
  self-heals even if the service died.
- **Digest/Outreach Sprint never arrives** — see "Notifications" above:
  `command -v termux-notification`, confirm the Termux:API *app* (not just
  the `termux-api` package) is installed, and check the Android 13+
  notification permission. `/notify` in the app shows whether Vamp thinks
  it's found `termux-notification` at all, and its "send now" buttons let
  you test the pipeline without waiting for 8am/Sunday 6pm.

## Backups

`~/.vamp/` holds all PII (SQLite DB + config + vault assets) in Termux's
private storage.

```sh
make backup   # or: .venv/bin/python -m vamp.cli backup
```

tarballs the SQLite DB (plus its WAL/SHM sidecars) and the vault's
`assets`/`epk` directories. If `termux-setup-storage` has been run (see
Install above), the tarball lands in `~/storage/shared/Vamp/backups/` —
Android shared storage — so Syncthing or a cloud-drive app of your choice
can sync it from there; Vamp itself never uploads anything. Before
`termux-setup-storage` (or on desktop), backups fall back to
`~/.vamp/backups/`. Override the destination entirely with
`VAMP_BACKUP_DIR=/some/path` in `~/.vamp/env`.
