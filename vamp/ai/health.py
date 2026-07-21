"""Health check + Termux fix instructions for the ``claude`` CLI provider.

CLAUDE.md: 'Health panel shows "Claude: logged in ✓ / missing — here's how
to fix it on Termux."' This module does the actual (cheap, cached-by-the-
caller — see ``vamp.ai.health_cache``) check; it never raises.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass

STATUS_OK = "ok"
STATUS_MISSING = "missing"
STATUS_NOT_LOGGED_IN = "not_logged_in"
STATUS_ERROR = "error"

STATUS_LABELS: dict[str, str] = {
    STATUS_OK: "Claude: logged in ✓",
    STATUS_MISSING: "Claude: CLI not found",
    STATUS_NOT_LOGGED_IN: "Claude: installed, not logged in",
    STATUS_ERROR: "Claude: error",
}

# CLAUDE.md / PLAN.md §9: Node via `pkg install nodejs-lts`, then the CLI via
# npm, then a one-time login against the household subscription.
#
# Two separate Termux-only gotchas baked into these steps:
#   - npm 11+ blocks install scripts by default (a supply-chain-security
#     change) — without allow-scripts, `npm install -g` silently skips a
#     package's postinstall step.
#   - claude-code itself switched to a native *glibc* binary starting at
#     2.1.113; Android's kernel refuses to exec glibc binaries at all
#     (Termux is bionic libc), so newer versions fail at runtime with
#     "claude native binary not installed" no matter what — pin the last
#     JS-based release instead. See anthropics/claude-code#50270; if
#     that issue reports upstream Android/bionic support landing, drop
#     the version pin below.
TERMUX_FIX_STEPS: tuple[str, ...] = (
    "pkg install -y nodejs-lts",
    "npm config set allow-scripts=@anthropic-ai/claude-code --location=user",
    "npm install -g @anthropic-ai/claude-code@2.1.112",
    "claude login   # opens a browser link once; uses your household subscription",
)

PING_PROMPT = "Reply with exactly the single word: PONG"
DEFAULT_HEALTH_TIMEOUT_SECONDS = 30

_UNAUTHENTICATED_HINTS = (
    "not logged in",
    "please log in",
    "log in with",
    "authenticat",
    "unauthorized",
    "401",
)


@dataclass(frozen=True)
class HealthStatus:
    status: str  # ok|missing|not_logged_in|error
    detail: str

    @property
    def label(self) -> str:
        return STATUS_LABELS.get(self.status, "Claude: unknown")

    @property
    def ok(self) -> bool:
        return self.status == STATUS_OK


def _looks_unauthenticated(text: str) -> bool:
    lowered = text.lower()
    return any(hint in lowered for hint in _UNAUTHENTICATED_HINTS)


def check_claude_health(
    binary: str = "claude", timeout_seconds: int = DEFAULT_HEALTH_TIMEOUT_SECONDS
) -> HealthStatus:
    """A real (small, cheap) round trip through the CLI — not just a PATH
    check — so "logged in" actually means logged in. Never raises."""
    if shutil.which(binary) is None:
        return HealthStatus(STATUS_MISSING, "claude CLI not found on PATH")

    try:
        proc = subprocess.run(
            [binary, "-p", PING_PROMPT, "--output-format", "json"],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return HealthStatus(STATUS_ERROR, f"claude timed out after {timeout_seconds}s")
    except OSError as exc:
        return HealthStatus(STATUS_ERROR, f"failed to run claude: {exc}")

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[:300]
        if _looks_unauthenticated(detail):
            return HealthStatus(STATUS_NOT_LOGGED_IN, detail or "not logged in")
        return HealthStatus(STATUS_ERROR, detail or f"exited {proc.returncode}")

    try:
        envelope = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return HealthStatus(STATUS_ERROR, "malformed JSON from claude --output-format json")

    if isinstance(envelope, dict) and envelope.get("is_error"):
        detail = str(envelope.get("result") or "")[:300]
        if _looks_unauthenticated(detail):
            return HealthStatus(STATUS_NOT_LOGGED_IN, detail or "not logged in")
        return HealthStatus(STATUS_ERROR, detail or "claude reported an error")

    return HealthStatus(STATUS_OK, "logged in")
