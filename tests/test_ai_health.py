from __future__ import annotations

import stat
from pathlib import Path

from vamp import db as vamp_db
from vamp.ai import health_cache
from vamp.ai.health import (
    STATUS_ERROR,
    STATUS_MISSING,
    STATUS_NOT_LOGGED_IN,
    STATUS_OK,
    check_claude_health,
)


def _fake_claude(tmp_path: Path, python_body: str) -> str:
    path = tmp_path / "claude"
    path.write_text(f"#!/usr/bin/env python3\n{python_body}\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return str(path)


def test_missing_binary_reports_missing():
    status = check_claude_health(binary="definitely-not-a-real-claude-binary")
    assert status.status == STATUS_MISSING
    assert not status.ok


def test_ok_binary_reports_ok(tmp_path: Path, monkeypatch):
    bin_dir = tmp_path
    _fake_claude(
        bin_dir,
        "import json\nprint(json.dumps({'is_error': False, 'result': 'PONG'}))",
    )
    monkeypatch.setenv("PATH", f"{bin_dir}:{__import__('os').environ['PATH']}")
    status = check_claude_health(binary="claude")
    assert status.status == STATUS_OK
    assert status.ok
    assert status.label == "Claude: logged in ✓"


def test_not_logged_in_binary_reports_not_logged_in(tmp_path: Path, monkeypatch):
    bin_dir = tmp_path
    _fake_claude(
        bin_dir,
        "import sys\nprint('Please log in with `claude login`', file=sys.stderr)\nsys.exit(1)",
    )
    monkeypatch.setenv("PATH", f"{bin_dir}:{__import__('os').environ['PATH']}")
    status = check_claude_health(binary="claude")
    assert status.status == STATUS_NOT_LOGGED_IN


def test_error_binary_reports_error(tmp_path: Path, monkeypatch):
    bin_dir = tmp_path
    _fake_claude(bin_dir, "import sys\nprint('boom', file=sys.stderr)\nsys.exit(2)")
    monkeypatch.setenv("PATH", f"{bin_dir}:{__import__('os').environ['PATH']}")
    status = check_claude_health(binary="claude")
    assert status.status == STATUS_ERROR


def test_health_cache_round_trip(vamp_home: Path):
    from vamp.config import load_config

    config = load_config(home=vamp_home)
    conn = vamp_db.get_connection(config.db_path)

    assert health_cache.get_cached_health(conn) == (None, None)

    status = health_cache.refresh_health(conn, binary="definitely-not-a-real-claude-binary")
    assert status.status == STATUS_MISSING

    cached_status, checked_at = health_cache.get_cached_health(conn)
    assert cached_status.status == STATUS_MISSING
    assert checked_at is not None
