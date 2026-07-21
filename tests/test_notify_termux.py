from __future__ import annotations

import stat
import textwrap
from pathlib import Path

from vamp.notify import termux


def _empty_path(tmp_path: Path, monkeypatch) -> None:
    empty_bin_dir = tmp_path / "empty-bin"
    empty_bin_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("PATH", str(empty_bin_dir))


def _fake_binary(tmp_path: Path, monkeypatch, script: str) -> None:
    bin_dir = tmp_path / "fake-bin"
    bin_dir.mkdir(exist_ok=True)
    binary = bin_dir / "termux-notification"
    binary.write_text(textwrap.dedent(script))
    binary.chmod(binary.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", str(bin_dir))


def test_missing_binary_logs_instead_of_failing(tmp_path: Path, monkeypatch):
    _empty_path(tmp_path, monkeypatch)

    result = termux.send_notification("Title", "Content")

    assert result.status == termux.STATUS_LOGGED
    assert result.ok
    assert "not found" in result.detail


def test_successful_send_reports_sent(tmp_path: Path, monkeypatch):
    _fake_binary(tmp_path, monkeypatch, "#!/bin/sh\nexit 0\n")

    result = termux.send_notification("Title", "Content", notification_id="vamp-test")

    assert result.status == termux.STATUS_SENT
    assert result.ok


def test_nonzero_exit_reports_error(tmp_path: Path, monkeypatch):
    _fake_binary(tmp_path, monkeypatch, "#!/bin/sh\necho 'boom' >&2\nexit 1\n")

    result = termux.send_notification("Title", "Content")

    assert result.status == termux.STATUS_ERROR
    assert not result.ok
    assert "boom" in result.detail


def test_timeout_reports_error(tmp_path: Path, monkeypatch):
    _fake_binary(tmp_path, monkeypatch, "#!/bin/sh\nwhile :; do :; done\n")

    result = termux.send_notification("Title", "Content", timeout_seconds=1)

    assert result.status == termux.STATUS_ERROR
    assert "timed out" in result.detail


def test_never_raises_on_missing_binary_object(tmp_path: Path, monkeypatch):
    # OSError path: PATH points somewhere real but the binary itself can't
    # execute (permission bits stripped) — still must not raise.
    _empty_path(tmp_path, monkeypatch)
    result = termux.send_notification("T", "C", binary="definitely-not-a-real-command")
    assert result.status == termux.STATUS_LOGGED
