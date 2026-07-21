"""Provider abstraction (PLAN.md §9/§12 M5): ``complete(system, prompt,
schema) -> dict``, with two implementations.

``ClaudeProvider`` shells out to the household-subscription CLI (``claude -p
--output-format json``); it never raises anything but ``ProviderError`` — CLI
missing, killed mid-run, timed out, non-JSON envelope, or a non-JSON/partial
result are all normalized into that one exception so callers have exactly
one failure mode to handle.

``NoneProvider`` is the heuristic/template fallback CLAUDE.md requires every
AI feature to keep working on. It never touches the network or a subprocess,
so it can't fail the way Claude can — instead of "understanding" the prompt,
it reads the structured ``schema["context"]`` each feature module supplies
alongside the natural-language prompt (which only ``ClaudeProvider`` reads).

``schema`` shape, by convention (not a validation library — CLAUDE.md: no
pydantic on Termux):
    {
        "task": "score_lead",                 # picks the heuristic branch
        "fields": {"score": "integer 0-100 ..."},   # told to Claude verbatim
        "context": {...},                      # structured data for NoneProvider
    }
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

CLAUDE_BIN = "claude"
DEFAULT_TIMEOUT_SECONDS = 60


class ProviderError(Exception):
    """Any provider failure — CLI missing, killed mid-run, timed out,
    malformed JSON. The one exception every caller needs to handle (see
    ``vamp.ai.router.run``, which catches this and falls back to
    ``NoneProvider``)."""


class Provider(Protocol):
    name: str

    def complete(self, system: str, prompt: str, schema: dict) -> dict: ...


# --------------------------------------------------------------- claude --


@dataclass
class ClaudeProvider:
    name: str = "claude"
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    binary: str = CLAUDE_BIN

    def complete(self, system: str, prompt: str, schema: dict) -> dict:
        fields = schema.get("fields", {})
        instructions = (
            f"{system}\n\n{prompt}\n\n"
            "Respond with ONLY a single JSON object (no markdown fences, no "
            "commentary before or after) with exactly these fields:\n"
            + "\n".join(f"- {name}: {desc}" for name, desc in fields.items())
        )
        try:
            proc = subprocess.run(
                [self.binary, "-p", instructions, "--output-format", "json"],
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            raise ProviderError(f"{self.binary} CLI not found on PATH") from exc
        except subprocess.TimeoutExpired as exc:
            raise ProviderError(f"{self.binary} timed out after {self.timeout_seconds}s") from exc
        except OSError as exc:
            raise ProviderError(f"failed to run {self.binary}: {exc}") from exc

        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()[:500]
            raise ProviderError(f"{self.binary} exited {proc.returncode}: {detail}")

        try:
            envelope = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise ProviderError(f"{self.binary} returned malformed JSON envelope") from exc

        if isinstance(envelope, dict) and envelope.get("is_error"):
            raise ProviderError(str(envelope.get("result") or "claude reported an error")[:500])

        result_text = envelope.get("result") if isinstance(envelope, dict) else None
        if not isinstance(result_text, str) or not result_text.strip():
            raise ProviderError("claude's JSON envelope had no 'result' text")

        payload = _extract_json_object(result_text)
        if payload is None:
            raise ProviderError("claude's result was not a JSON object")
        return payload


def _extract_json_object(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = text.removesuffix("```").strip()
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            obj = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return obj if isinstance(obj, dict) else None


# ---------------------------------------------------------------- none --


@dataclass
class NoneProvider:
    """Heuristics/templates — always available, always tested. This is the
    degraded path (CLAUDE.md: "every AI feature must work (degraded) when
    no provider is available"), not a lesser Claude; it never raises."""

    name: str = "none"

    def complete(self, system: str, prompt: str, schema: dict) -> dict:
        del system, prompt  # NoneProvider reads schema["context"], not prose
        task = schema.get("task")
        handler = _HEURISTICS.get(task)
        if handler is None:
            raise ProviderError(f"no heuristic template registered for task {task!r}")
        return handler(schema.get("context") or {})


# ---------------------------------------------------- heuristic templates --

PAYING_KINDS = {"flat", "hourly", "salary"}
_LOCAL_AREA_RE = re.compile(
    r"\bokc\b|oklahoma city|edmond|moore|norman|yukon|midwest city|bethany|del city",
    re.IGNORECASE,
)
_FIT_RE = re.compile(r"piano|keyboard|keys|pianist|accompanist|vocal|singer|improv", re.IGNORECASE)


def _heuristic_score_lead(ctx: dict) -> dict:
    score = 50
    flags: list[str] = []
    why: list[str] = []

    pay_kind = (ctx.get("pay_kind") or "unknown").lower()
    if pay_kind in PAYING_KINDS:
        score += 20
        why.append("confirmed pay")
        pay_min = ctx.get("pay_min")
        if isinstance(pay_min, int | float) and pay_min >= 100:
            score += 10
            why.append(f"pay_min ${pay_min:g} clears a reasonable floor")
    elif pay_kind == "unpaid":
        score -= 30
        flags.append("unpaid")
        why.append("no pay offered")
    elif pay_kind == "tips":
        score -= 10
        flags.append("tips-only")
        why.append("tips only, no guarantee")
    else:
        why.append("pay unclear")

    text = f"{ctx.get('title') or ''} {ctx.get('description') or ''}"
    if _FIT_RE.search(text):
        score += 10
        why.append("matches piano/keys/vocal/improv fit tags")

    location = ctx.get("location") or ""
    if _LOCAL_AREA_RE.search(location) or _LOCAL_AREA_RE.search(text):
        score += 5
        why.append("in the OKC metro")

    deadline = ctx.get("deadline")
    if deadline:
        due = _parse_date(deadline)
        if due is not None and 0 <= (due - datetime.now(UTC).replace(tzinfo=None)).days <= 14:
            flags.append("deadline-soon")
            why.append("deadline within two weeks")

    score = max(0, min(100, score))
    rationale = "; ".join(why) if why else "no strong signal either way"
    return {"score": score, "rationale": rationale, "flags": flags}


def _parse_date(value: str) -> datetime | None:
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value[: len(fmt) + 2].strip(), fmt)
        except ValueError:
            continue
    return None


def _heuristic_degree_review(ctx: dict) -> dict:
    # The degraded path never overturns the M1 heuristic exclusion — it
    # takes a second AI opinion to open a degree wall, and there is no AI
    # here. Standing pat (override=False) is the safe default.
    return {"override": False, "reasoning": "no AI provider available; heuristic exclusion stands"}


def _heuristic_requirement_extraction(ctx: dict) -> dict:
    # The M3 heuristic pass already ran on this lead's text before an AI
    # pass would ever be attempted; with no provider there is nothing new
    # to merge, so this is an intentional no-op.
    return {"requirements": []}


def _heuristic_draft_pitch(ctx: dict) -> dict:
    name = ctx.get("prospect_name") or "there"
    angle = ctx.get("angle")
    voice_sample = ctx.get("voice_sample")
    display_name = ctx.get("display_name") or "Kaelyn"
    bio = ctx.get("bio")

    lines = [f"Hi {name},"]
    lines.append("")
    if angle:
        lines.append(f"{angle.rstrip('.')} — I'd love to talk about bringing live piano in.")
    else:
        lines.append(
            "I'm a local pianist/vocalist and wanted to reach out about live music at your place."
        )
    if bio:
        lines.append("")
        lines.append(bio.strip())
    lines.append("")
    lines.append("Would you be open to a quick conversation about what that could look like?")
    lines.append("")
    lines.append(f"Thanks for your time,\n{display_name}")
    body = "\n".join(lines)
    if voice_sample:
        body += (
            "\n\n[Heuristic draft — no AI provider available. Personalize using your voice "
            "sample before sending; this template does not attempt to match your voice.]"
        )
    subject = f"Live piano at {name}?" if name != "there" else "Live piano?"
    return {"subject": subject, "body": body}


def _heuristic_draft_bio(ctx: dict) -> dict:
    display_name = ctx.get("display_name") or "the artist"
    instrument = ctx.get("instrument") or "pianist"
    home_area = ctx.get("home_area") or "the Oklahoma City metro"
    voice_sample = ctx.get("voice_sample")

    base = (
        f"{display_name} is a {instrument} based in {home_area}, performing "
        f"solo piano, vocals, and free improvisation for venues, private events, "
        f"and worship communities."
    )
    if voice_sample:
        note = " [Heuristic draft — rewrite in your own voice; see your voice sample.]"
    else:
        note = ""
    bio_50 = _truncate_words(base, 50) + note
    bio_150 = (
        base + f" {display_name} draws on a background spanning classical training, "
        f"jazz standards, and original songwriting, equally at home reading a "
        f"chart cold or improvising a set from nothing." + note
    )
    bio_300 = (
        bio_150 + f" Recent and ongoing work includes solo cocktail-hour sets, worship "
        f"accompaniment, and collaborations across the {home_area} scene. "
        f"{display_name} is available for weddings, private events, church "
        f"services, and venues looking to add live piano."
    )
    return {"bio_50": bio_50, "bio_150": bio_150, "bio_300": bio_300}


def _truncate_words(text: str, limit: int) -> str:
    words = text.split()
    if len(words) <= limit:
        return text
    return " ".join(words[:limit]) + "…"


def _heuristic_draft_followup(ctx: dict) -> dict:
    name = ctx.get("prospect_name") or "there"
    display_name = ctx.get("display_name") or "Kaelyn"
    body = (
        f"Hi {name},\n\n"
        "Just following up on my note about live piano — no pressure at all, "
        "just wanted to keep the door open in case the timing's better now.\n\n"
        f"Thanks,\n{display_name}\n\n"
        "[Heuristic draft — no AI provider available.]"
    )
    return {"subject": f"Following up — live piano at {name}?", "body": body}


def _heuristic_draft_sub_availability(ctx: dict) -> dict:
    display_name = ctx.get("display_name") or "Kaelyn"
    date = ctx.get("date") or "this Sunday"
    body = (
        f"Hi — just checking in: I'm available to sub on {date} if you need a "
        f"pianist. Let me know!\n\n{display_name}\n\n"
        "[Heuristic draft — no AI provider available.]"
    )
    return {"subject": f"Available to sub {date}", "body": body}


_HEURISTICS = {
    "score_lead": _heuristic_score_lead,
    "degree_review": _heuristic_degree_review,
    "requirement_extraction": _heuristic_requirement_extraction,
    "draft_pitch": _heuristic_draft_pitch,
    "draft_bio": _heuristic_draft_bio,
    "draft_followup": _heuristic_draft_followup,
    "draft_sub_availability": _heuristic_draft_sub_availability,
}

# Re-exported for callers that want to compute "is this deadline soon"
# without duplicating the heuristic's window.
DEADLINE_SOON_WINDOW = timedelta(days=14)
