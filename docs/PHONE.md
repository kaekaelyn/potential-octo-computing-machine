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
git clone https://github.com/kaekaelyn/potential-octo-computing-machine vamp
cd vamp
./install.sh
```

(`pkg install -y git python make` can pull in a chunk of Termux's build
toolchain — `clang`/`llvm`/`lld`/`pkg-config` — as dependencies the first
time you install `python` on a fresh Termux. That's expected, not a
failure; let it finish.)

(Cloning under a different fork or URL? Swap the URL above, but don't
paste a bare `<placeholder>` — angle brackets are shell redirection
syntax, so `git clone <repo-url> vamp` fails immediately with
`bash: repo-url: No such file or directory` instead of prompting you to
fill anything in.)

## What `install.sh` does on Termux

1. Creates `.venv` in the repo and installs `requirements.txt` (pure
   Python only — see CLAUDE.md "Hard rules" — so this step never needs a
   compiler).
2. Initializes `~/.vamp/env` (config, mode 600) and the SQLite database
   at `~/.vamp/vamp.db`, applying migrations.
3. Installs `termux-services` and `termux-api` (via `pkg`) if the
   `sv-enable`/`termux-wake-lock` commands aren't already on `PATH`.
4. Exports `SVDIR=$PREFIX/var/service` (and `LOGDIR`) for the rest of the
   script, and appends the same `export SVDIR=...` to `~/.bashrc` if it's
   not there already. `termux-services`' `sv`/`sv-enable`/`sv-disable` all
   resolve a bare service name (`vamp`) through `$SVDIR`, falling back to
   runit's compiled-in `/service` default — which doesn't exist under
   Termux — if it's unset. It's normally exported by
   `$PREFIX/etc/profile.d/start-services.sh`, but that only runs for
   interactive shells that source it; a non-interactive `bash install.sh`
   run never does, and apparently not every interactive Termux session
   reliably does either. Without this, every `sv-enable`/`sv up`/
   `sv status` fails with "unable to change to service directory: file
   does not exist" — regardless of anything else being correct.
5. Writes a [runit](http://smarden.org/runit/) service definition to
   `$SVDIR/vamp/run` (rendered from `termux/service-run.template`) that:
   `cd`s into the repo, takes a `termux-wake-lock`, and `exec`s
   `.venv/bin/python -m vamp.wsgi` — logging to `~/.vamp/service.log`.
   `exec` (not a backgrounded subprocess) is required: runit supervises
   the service's own PID, and a script that daemonizes/forks breaks that
   contract. Unlike vanilla/Void-Linux runit, `termux-services` has no
   `/etc/sv` staging directory or symlink step — `$SVDIR` is where
   `runsvdir` watches *and* where a service's own directory has to live;
   an earlier version of this script wrote to `$PREFIX/etc/sv/vamp`
   assuming something would symlink it into place, which nothing did.
   `install.sh` cleans up that stale location if it finds it.
6. Runs `sv-enable vamp` (termux-services' own script: `rm -f
   $SVDIR/vamp/down; sv up vamp` — clears the "stay stopped" marker, if
   any, and starts it), which both starts the service now and marks it
   to persist across `sv` restarts.
7. Writes `~/.termux/boot/start-vamp.sh` (rendered from
   `termux/boot-start.template`), which Termux:Boot runs on every device
   boot. Boot scripts don't run as a login shell either, so they export
   `SVDIR` themselves too; the script also starts `runsvdir` if it isn't
   running, waits briefly, then `sv-enable`/`sv up`s the vamp service —
   plus its own wake-lock, in case the app was killed and this is a cold
   boot.

## Verifying it worked

`install.sh` appends `export SVDIR=$PREFIX/var/service` to `~/.bashrc`, so
a **newly opened** Termux session should already have it — but since
that's exactly the thing that's gone wrong before, set it explicitly here
too rather than assume:

```sh
export SVDIR="$PREFIX/var/service"
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

- **`sv status vamp`/`sv up vamp`/`sv-enable vamp` report `fail: vamp:
  unable to change to service directory: file does not exist`** — two
  possible causes, and it's worth checking both:
  1. **`$SVDIR` isn't set.** `sv`/`sv-enable` resolve a bare service name
     through the `SVDIR` env var, falling back to runit's compiled-in
     `/service` (which doesn't exist under Termux) if it's unset — this
     is normally exported by an interactive shell sourcing
     `$PREFIX/etc/profile.d/start-services.sh`, but that doesn't always
     reliably happen (and never happens for a non-interactive script).
     Run `echo "$SVDIR"` — if it's empty, that's it. Fix it for the
     current shell with `export SVDIR="$PREFIX/var/service"`, and
     confirm `install.sh` added the same line to `~/.bashrc` (`grep
     SVDIR ~/.bashrc`) so future sessions don't need it typed by hand.
  2. **You're on a checkout from before this was fixed.** An earlier
     `install.sh` wrote the service to `$PREFIX/etc/sv/vamp` and expected
     `sv-enable` to symlink it into `$SVDIR`; `termux-services`' real
     `sv-enable` doesn't do that (it's just `rm -f $SVDIR/vamp/down; sv
     up vamp`), so `$SVDIR/vamp` never existed and every `sv` command
     against it failed no matter how many times you retried or restarted
     Termux. `git pull && ./install.sh` fixes it — the current script
     writes directly to `$SVDIR/vamp` and cleans up the stale `etc/sv`
     location.
- **`sv status vamp`/`sv up vamp` report `warning: vamp: unable to open
  supervise/ok: file does not exist`** (note: *unable to open*, not
  *unable to change to* — a different error from the one above) — this
  means `$SVDIR` and the service directory are both correct, but
  `runsvdir` hasn't spawned its supervisor process for `vamp` yet.
  `runsvdir` rescans its directory periodically rather than reacting to a
  just-created service directory instantly, so calling `sv up` immediately
  after `install.sh` creates it can lose that race. `install.sh` and the
  boot script both retry `sv up` for several seconds now rather than
  failing on the first attempt; if you still see this after `git pull &&
  ./install.sh`, just wait a few seconds and rerun `sv status vamp` by
  hand — it resolves itself once `runsvdir` catches up.
- **`sv-enable: command not found` right after install** — the
  `termux-services` package adds shell integration that a running shell
  won't pick up until it restarts. Close and reopen Termux, then rerun
  `export SVDIR="$PREFIX/var/service" && sv-enable vamp && sv up vamp`.
- **Service enabled but not running (`$SVDIR` is set and the directory is
  correct)** — check `~/.vamp/service.log` and `cat $SVDIR/vamp/run` for
  a stale path (e.g. the repo was moved after install; rerun
  `./install.sh` to regenerate the run script with the current path).
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
