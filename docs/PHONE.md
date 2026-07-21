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
   and boot-time autostart respectively.
3. Open Termux:Boot once after installing it so Android registers it as
   a boot-completed receiver.
4. In Android Settings → Apps → Termux → Battery, exempt Termux from
   battery optimization ("Unrestricted" / "Don't optimize"). Without
   this, Android will kill the background service regardless of
   wake-locks or boot scripts.

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

## Backups

`~/.vamp/` holds all PII (SQLite DB + config) in Termux's private
storage. Backups (`vamp backup`, landing in M3) tarball this to Android
shared storage via `termux-setup-storage`; from there, Syncthing or a
cloud-drive app of your choice can sync it — Vamp itself never uploads
anything.
