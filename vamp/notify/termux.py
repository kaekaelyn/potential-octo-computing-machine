"""``termux-notification`` adapter (PLAN.md §2/§9: "Notify: termux-notification
(Termux:API) — fully local"). Real Android notifications when the Termux:API
CLI is on PATH; a log-only no-op fallback everywhere else (desktop dev, CI,
or a phone without the Termux:API app/package yet) — CLAUDE.md's portability
rule: core behavior must run on desktop Linux too.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass

logger = logging.getLogger("vamp.notify")

STATUS_SENT = "sent"
STATUS_LOGGED = "logged"
STATUS_ERROR = "error"

DEFAULT_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class NotifyResult:
    status: str  # sent|logged|error
    detail: str

    @property
    def ok(self) -> bool:
        return self.status in (STATUS_SENT, STATUS_LOGGED)


def send_notification(
    title: str,
    content: str,
    *,
    notification_id: str | None = None,
    binary: str = "termux-notification",
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> NotifyResult:
    """Fire a real Android notification. Never raises: no ``termux-notification``
    on ``PATH`` logs the message and reports ``logged`` rather than failing —
    the no-op fallback this module exists to guarantee."""
    if shutil.which(binary) is None:
        logger.info("notify (no %s on PATH): %s — %s", binary, title, content)
        return NotifyResult(STATUS_LOGGED, f"{binary} not found on PATH; logged instead")

    cmd = [binary, "--title", title, "--content", content]
    if notification_id:
        cmd += ["--id", str(notification_id)]

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout_seconds, check=False
        )
    except subprocess.TimeoutExpired:
        detail = f"{binary} timed out after {timeout_seconds}s"
        logger.warning(detail)
        return NotifyResult(STATUS_ERROR, detail)
    except OSError as exc:
        detail = f"failed to run {binary}: {exc}"
        logger.warning(detail)
        return NotifyResult(STATUS_ERROR, detail)

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[:300] or f"exited {proc.returncode}"
        logger.warning("%s exited %s: %s", binary, proc.returncode, detail)
        return NotifyResult(STATUS_ERROR, detail)

    return NotifyResult(STATUS_SENT, "sent")
