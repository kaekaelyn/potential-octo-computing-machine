from __future__ import annotations

import pytest

from vamp.ai.provider import NoneProvider, Provider, ProviderError
from vamp.ai.router import run


class _AlwaysFails:
    name = "claude"

    def complete(self, system, prompt, schema):
        raise ProviderError("simulated CLI failure")


class _AlwaysSucceeds:
    name = "claude"

    def complete(self, system, prompt, schema):
        return {"ok": True}


def test_run_returns_claude_result_when_it_succeeds():
    result, used = run(_AlwaysSucceeds(), "s", "p", {"task": "score_lead", "context": {}})
    assert used == "claude"
    assert result == {"ok": True}


def test_run_falls_back_to_none_when_claude_fails():
    schema = {"task": "score_lead", "context": {"pay_kind": "unknown"}}
    result, used = run(_AlwaysFails(), "s", "p", schema)
    assert used == "none"
    assert "score" in result


def test_run_never_raises_provider_error_from_claude_failure():
    schema = {"task": "score_lead", "context": {}}
    # This must not raise, even though the injected provider always raises.
    run(_AlwaysFails(), "s", "p", schema)


def test_run_propagates_when_none_provider_itself_fails():
    schema = {"task": "no-such-task", "context": {}}
    with pytest.raises(ProviderError):
        run(NoneProvider(), "s", "p", schema)


def test_none_provider_satisfies_provider_protocol():
    provider: Provider = NoneProvider()
    assert provider.name == "none"
