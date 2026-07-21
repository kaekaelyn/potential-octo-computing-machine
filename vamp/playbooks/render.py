"""A tiny, dependency-free Markdown→HTML renderer for playbook bodies.

Pure Python (CLAUDE.md: no compiled deps; also no need to pull a markdown
library for the small subset the playbooks use). Everything is HTML-escaped
first, so playbook content can never inject markup — the renderer only ever
*adds* a fixed set of safe tags. Supported: ATX headings, unordered/ordered
lists, blockquotes, horizontal rules, paragraphs, and inline bold/italic/code/
links.
"""

from __future__ import annotations

import html
import re

_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
_CODE = re.compile(r"`([^`]+)`")
# [text](http://safe-url) — only http(s)/mailto targets are allowed through.
_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+|mailto:[^)\s]+)\)")


def _inline(text: str) -> str:
    escaped = html.escape(text, quote=False)
    escaped = _CODE.sub(r"<code>\1</code>", escaped)
    escaped = _BOLD.sub(r"<strong>\1</strong>", escaped)
    escaped = _ITALIC.sub(r"<em>\1</em>", escaped)

    def _link(match: re.Match) -> str:
        label, url = match.group(1), match.group(2)
        return f'<a href="{url}" target="_blank" rel="noopener noreferrer">{label}</a>'

    return _LINK.sub(_link, escaped)


def render_markdown(text: str) -> str:
    """Render a constrained Markdown subset to a safe HTML fragment."""
    lines = text.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    para: list[str] = []
    list_type: str | None = None  # "ul" | "ol"

    def flush_para() -> None:
        if para:
            out.append(f"<p>{' '.join(_inline(line) for line in para)}</p>")
            para.clear()

    def close_list() -> None:
        nonlocal list_type
        if list_type:
            out.append(f"</{list_type}>")
            list_type = None

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()

        if not stripped:
            flush_para()
            close_list()
            continue

        heading = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if heading:
            flush_para()
            close_list()
            level = len(heading.group(1))
            out.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
            continue

        if stripped in ("---", "***", "___"):
            flush_para()
            close_list()
            out.append("<hr>")
            continue

        ul = re.match(r"^[-*]\s+(.*)$", stripped)
        ol = re.match(r"^\d+\.\s+(.*)$", stripped)
        if ul or ol:
            flush_para()
            want = "ul" if ul else "ol"
            if list_type != want:
                close_list()
                out.append(f"<{want}>")
                list_type = want
            item = (ul or ol).group(1)
            out.append(f"<li>{_inline(item)}</li>")
            continue

        if stripped.startswith(">"):
            flush_para()
            close_list()
            out.append(f"<blockquote>{_inline(stripped[1:].strip())}</blockquote>")
            continue

        para.append(stripped)

    flush_para()
    close_list()
    return "\n".join(out)
