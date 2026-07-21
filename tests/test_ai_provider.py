from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from vamp.ai.provider import ClaudeProvider, NoneProvider, ProviderError

SCHEMA = {"task": "score_lead", "fields": {"score": "int"}, "context": {}}


def _fake_claude(tmp_path: Path, python_body: str) -> str:
    """Writes a fake `claude` executable that's actually a tiny Python
    script, so envelope construction happens in real Python (no shell
    quoting gymnastics) — mirrors "kill the CLI mid-run" style tests."""
    path = tmp_path / "claude"
    path.write_text(f"#!/usr/bin/env python3\n{python_body}\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return str(path)


def test_claude_provider_missing_binary_raises_provider_error():
    provider = ClaudeProvider(binary="definitely-not-a-real-claude-binary")
    with pytest.raises(ProviderError, match="not found"):
        provider.complete("system", "prompt", SCHEMA)


def test_claude_provider_parses_result_json(tmp_path: Path):
    bin_path = _fake_claude(
        tmp_path,
        "import json, sys\n"
        "print(json.dumps({'is_error': False, 'result': json.dumps({'score': 42})}))",
    )
    provider = ClaudeProvider(binary=bin_path)
    result = provider.complete("system", "prompt", SCHEMA)
    assert result == {"score": 42}


def test_claude_provider_strips_markdown_fences(tmp_path: Path):
    bin_path = _fake_claude(
        tmp_path,
        "import json\n"
        "inner = '```json\\n' + json.dumps({'score': 7}) + '\\n```'\n"
        "print(json.dumps({'is_error': False, 'result': inner}))",
    )
    provider = ClaudeProvider(binary=bin_path)
    result = provider.complete("system", "prompt", SCHEMA)
    assert result == {"score": 7}


def test_claude_provider_nonzero_exit_raises(tmp_path: Path):
    bin_path = _fake_claude(tmp_path, "import sys\nprint('boom', file=sys.stderr)\nsys.exit(1)")
    provider = ClaudeProvider(binary=bin_path)
    with pytest.raises(ProviderError, match="boom"):
        provider.complete("system", "prompt", SCHEMA)


def test_claude_provider_killed_mid_run_raises(tmp_path: Path):
    bin_path = _fake_claude(tmp_path, "import os, signal\nos.kill(os.getpid(), signal.SIGKILL)")
    provider = ClaudeProvider(binary=bin_path)
    with pytest.raises(ProviderError):
        provider.complete("system", "prompt", SCHEMA)


def test_claude_provider_malformed_envelope_raises(tmp_path: Path):
    bin_path = _fake_claude(tmp_path, "print('not json at all {{{')")
    provider = ClaudeProvider(binary=bin_path)
    with pytest.raises(ProviderError, match="malformed JSON"):
        provider.complete("system", "prompt", SCHEMA)


def test_claude_provider_non_json_result_text_raises(tmp_path: Path):
    bin_path = _fake_claude(
        tmp_path,
        "import json\nprint(json.dumps({'is_error': False, 'result': 'just some prose, no JSON'}))",
    )
    provider = ClaudeProvider(binary=bin_path)
    with pytest.raises(ProviderError, match="not a JSON object"):
        provider.complete("system", "prompt", SCHEMA)


def test_claude_provider_is_error_envelope_raises(tmp_path: Path):
    bin_path = _fake_claude(
        tmp_path, "import json\nprint(json.dumps({'is_error': True, 'result': 'rate limited'}))"
    )
    provider = ClaudeProvider(binary=bin_path)
    with pytest.raises(ProviderError, match="rate limited"):
        provider.complete("system", "prompt", SCHEMA)


def test_claude_provider_timeout_raises(tmp_path: Path):
    bin_path = _fake_claude(tmp_path, "import time\ntime.sleep(5)")
    provider = ClaudeProvider(binary=bin_path, timeout_seconds=1)
    with pytest.raises(ProviderError, match="timed out"):
        provider.complete("system", "prompt", SCHEMA)


def test_none_provider_score_lead_heuristic():
    provider = NoneProvider()
    schema = {
        "task": "score_lead",
        "fields": {},
        "context": {"pay_kind": "flat", "pay_min": 200, "title": "Pianist", "description": ""},
    }
    result = provider.complete("s", "p", schema)
    assert 0 <= result["score"] <= 100
    assert isinstance(result["flags"], list)


def test_none_provider_unknown_task_raises():
    provider = NoneProvider()
    with pytest.raises(ProviderError, match="no heuristic template"):
        provider.complete("s", "p", {"task": "does-not-exist", "context": {}})


def test_none_provider_degree_review_never_overrides():
    provider = NoneProvider()
    result = provider.complete("s", "p", {"task": "degree_review", "context": {"text": "..."}})
    assert result["override"] is False


def test_none_provider_draft_pitch_produces_subject_and_body():
    provider = NoneProvider()
    schema = {
        "task": "draft_pitch",
        "context": {"prospect_name": "The Grand Hotel", "angle": "has a lobby grand nobody plays"},
    }
    result = provider.complete("s", "p", schema)
    assert result["subject"]
    assert "Grand Hotel" in result["body"]


def test_none_provider_draft_bio_produces_three_lengths():
    provider = NoneProvider()
    schema = {
        "task": "draft_bio",
        "context": {"display_name": "Kaelyn", "instrument": "pianist", "home_area": "OKC"},
    }
    result = provider.complete("s", "p", schema)
    assert len(result["bio_50"].split()) <= 60
    assert len(result["bio_150"]) > len(result["bio_50"])
    assert len(result["bio_300"]) > len(result["bio_150"])


def test_none_provider_json_roundtrip_smoke():
    # NoneProvider never touches json module directly for output, but every
    # heuristic dict must itself be JSON-serializable (drafts are cached as
    # content_json) — cheap regression guard.
    provider = NoneProvider()
    for task, ctx in (
        ("score_lead", {}),
        ("degree_review", {}),
        ("requirement_extraction", {}),
        ("draft_pitch", {}),
        ("draft_bio", {}),
        ("draft_followup", {}),
        ("draft_sub_availability", {}),
    ):
        result = provider.complete("s", "p", {"task": task, "context": ctx})
        json.dumps(result)
