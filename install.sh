#!/usr/bin/env bash
# Vamp installer. On Termux: sets up the venv, registers a termux-services
# runit service, a Termux:Boot start script, and a wake-lock. On desktop
# Linux: sets up the venv and the SQLite schema so `make dev` works — no
# service/boot machinery, since that's Termux-only (CLAUDE.md portability
# rule).
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

log() { printf '==> %s\n' "$1"; }
warn() { printf 'WARNING: %s\n' "$1" >&2; }

setup_venv() {
    log "Setting up virtualenv (.venv) and installing requirements.txt"
    python3 -m venv "$REPO_DIR/.venv"
    "$REPO_DIR/.venv/bin/python" -m pip install --upgrade pip -q
    "$REPO_DIR/.venv/bin/python" -m pip install -r "$REPO_DIR/requirements.txt" -q
}

init_config_and_db() {
    log "Initializing ~/.vamp config and SQLite schema"
    "$REPO_DIR/.venv/bin/python" - <<'PYEOF'
from vamp.config import load_config
from vamp.db import get_connection

config = load_config()
conn = get_connection(config.db_path)
conn.close()
print(f"  config: {config.home / 'env'}")
print(f"  db:     {config.db_path}")
PYEOF
}

install_termux() {
    log "Termux detected (TERMUX_VERSION=$TERMUX_VERSION)"

    if ! command -v sv-enable >/dev/null 2>&1 || ! command -v termux-wake-lock >/dev/null 2>&1; then
        log "Installing termux-services and termux-api packages"
        pkg install -y termux-services termux-api
    fi

    # termux-services' own sv-enable is just `rm -f "$SVDIR/$1/down"; sv up $1`
    # (SVDIR = $PREFIX/var/service) — unlike vanilla/Void-Linux runit, nothing
    # symlinks a staging directory into place for you. The service's own
    # directory (with its `run` script) has to already live directly under
    # $SVDIR, or every sv-enable/sv up/sv status fails with "unable to change
    # to service directory: file does not exist", deterministically, every
    # time — not a timing issue.
    local svdir="$PREFIX/var/service"
    local sv_dir="$svdir/vamp"
    rm -rf "$PREFIX/etc/sv/vamp"  # stale location from an earlier (broken) version of this script
    log "Writing runit service to $sv_dir/run"
    mkdir -p "$sv_dir"
    sed "s|__REPO_DIR__|$REPO_DIR|g" "$REPO_DIR/termux/service-run.template" > "$sv_dir/run"
    chmod +x "$sv_dir/run"

    log "Writing Termux:Boot start script to ~/.termux/boot/start-vamp.sh"
    mkdir -p "$HOME/.termux/boot"
    cp "$REPO_DIR/termux/boot-start.template" "$HOME/.termux/boot/start-vamp.sh"
    chmod +x "$HOME/.termux/boot/start-vamp.sh"

    log "Enabling and starting the vamp service"
    if command -v sv-enable >/dev/null 2>&1; then
        # termux-services was potentially just installed moments ago (above) —
        # its runsvdir supervisor may not be up yet in this shell. The boot
        # script already guards against this same race; mirror it here.
        if ! pgrep -f "runsvdir $svdir" >/dev/null 2>&1; then
            log "runsvdir not running yet — starting it"
            runsvdir "$svdir" >> "$HOME/.vamp/runsvdir.log" 2>&1 &
            sleep 2
        fi
        sv-enable vamp || warn "sv-enable failed — restart Termux (PATH refresh) and rerun install.sh"
        sv up vamp 2>/dev/null || warn "sv up vamp failed — check 'sv status vamp' after restarting Termux"
    else
        warn "sv-enable not found on PATH yet — restart Termux and run: sv-enable vamp && sv up vamp"
    fi

    cat <<EOF

Next steps (see docs/PHONE.md for details):
  1. Install the Termux:Boot app from F-Droid (not Play Store) and open it
     once so it registers with Android.
  2. Exempt Termux from battery optimization in Android settings.
  3. If 'sv-enable'/'sv' were reported as not found above, restart Termux
     and rerun: sv-enable vamp && sv up vamp
  4. Open http://127.0.0.1:8485 in a browser and "Add to home screen".
EOF
}

install_desktop() {
    log "No Termux detected — desktop-dev fallback"
    cat <<EOF

Vamp is set up for local development. There is no background service on
desktop (that's Termux-only); start it yourself with:
  make dev
then open http://127.0.0.1:8485
EOF
}

main() {
    setup_venv
    init_config_and_db

    if [ -n "${TERMUX_VERSION:-}" ]; then
        install_termux
    else
        install_desktop
    fi

    log "Install complete."
}

main "$@"
