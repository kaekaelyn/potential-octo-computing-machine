"""The one place CLAUDE.md's degradation rule is enforced structurally:
every AI feature calls ``run()`` instead of a provider directly, so a
``ProviderError`` from Claude — CLI missing, killed mid-run, malformed
JSON, whatever — never reaches feature code. It always gets a usable
result, plus the name of whichever provider actually produced it (cached
alongside the result so callers/tests can tell heuristic output from a
real AI answer).
"""

from __future__ import annotations

import logging

from vamp.ai.provider import ClaudeProvider, NoneProvider, Provider, ProviderError
from vamp.config import Config

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 60


def get_provider(vamp_config: Config | None) -> Provider:
    """The provider to attempt first. Always Claude — ``run()`` below is
    what falls back to heuristics on failure, per-call, so a CLI that comes
    back mid-batch is used again immediately rather than staying benched
    for the rest of the run."""
    timeout = DEFAULT_TIMEOUT_SECONDS
    if vamp_config is not None:
        raw = vamp_config.get("VAMP_AI_TIMEOUT_SECONDS")
        if raw:
            try:
                timeout = int(raw)
            except ValueError:
                pass
    return ClaudeProvider(timeout_seconds=timeout)


def run(provider: Provider, system: str, prompt: str, schema: dict) -> tuple[dict, str]:
    """Call ``provider``; on any ``ProviderError``, fall back to
    ``NoneProvider``. Returns ``(result, provider_name_used)``. Never raises
    a ``ProviderError`` — that is the whole point of this function existing.
    """
    try:
        return provider.complete(system, prompt, schema), provider.name
    except ProviderError as exc:
        if provider.name == "none":
            raise  # the heuristic path itself must never fail to degrade
        logger.warning("AI provider %r failed (%s); falling back to none", provider.name, exc)
        fallback = NoneProvider()
        return fallback.complete(system, prompt, schema), fallback.name
