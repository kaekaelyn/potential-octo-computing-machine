"""EPK export: one self-contained static HTML file generated from the
vault (PLAN.md §5) — she can send it as an attachment, print to PDF, or
host anywhere. Vamp never publishes or hosts it itself (CLAUDE.md: no
cloud services).

Local image files are embedded as base64 data URIs so the file is truly
self-contained; local text files (bios, the compiled repertoire list) are
inlined as text; anything else (a linked video, a PDF rate card) becomes
a plain link — printable/shareable, not embedded.
"""

from __future__ import annotations

import base64
import html
import mimetypes
import sqlite3
from pathlib import Path

from vamp.vault.assets import is_local_file

_STYLE = """
  body { font-family: Georgia, 'Times New Roman', serif; max-width: 42rem;
         margin: 2rem auto; padding: 0 1.25rem; color: #1b1b1b; line-height: 1.5; }
  h1 { margin-bottom: 0; }
  .tagline { color: #6b6b6b; font-style: italic; margin-top: 0.2rem; }
  img.headshot { max-width: 100%; border-radius: 0.5rem; margin: 1.5rem 0; }
  section { margin: 2rem 0; }
  section h2 { border-bottom: 1px solid #ccc; padding-bottom: 0.25rem; }
  pre { white-space: pre-wrap; font-family: inherit; margin: 0; }
  ul { padding-left: 1.25rem; }
"""


def _asset_by_kind(conn: sqlite3.Connection, kind: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM assets WHERE kind = ? AND ready = 1 "
        "ORDER BY updated_at DESC, id DESC LIMIT 1",
        (kind,),
    ).fetchone()


def _assets_by_kind(conn: sqlite3.Connection, kind: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM assets WHERE kind = ? AND ready = 1 ORDER BY updated_at DESC, id DESC",
        (kind,),
    ).fetchall()


def _embed_image(path_or_url: str | None) -> str | None:
    if not path_or_url or not is_local_file(path_or_url):
        return None
    path = Path(path_or_url)
    if not path.exists() or not path.is_file():
        return None
    mime, _ = mimetypes.guess_type(path.name)
    if not mime or not mime.startswith("image/"):
        return None
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def _inline_text(path_or_url: str | None) -> str | None:
    if not path_or_url or not is_local_file(path_or_url):
        return None
    path = Path(path_or_url)
    if not path.exists() or path.suffix.lower() not in (".txt", ".md"):
        return None
    return path.read_text()


def _esc(value: str | None) -> str:
    return html.escape(value or "")


def epk_readiness(conn: sqlite3.Connection) -> dict:
    """What the EPK export would include right now — used to show the
    "missing before you export" hint on the vault EPK page."""
    have_bio = _asset_by_kind(conn, "bio") is not None
    have_headshot = _asset_by_kind(conn, "headshot") is not None
    have_video = bool(_assets_by_kind(conn, "live_video"))
    return {
        "bio": have_bio,
        "headshot": have_headshot,
        "live_video": have_video,
        "core_ready": have_bio and have_headshot and have_video,
    }


def generate_epk_html(conn: sqlite3.Connection, artist_name: str = "Kaelyn") -> str:
    bio = _asset_by_kind(conn, "bio")
    headshot = _asset_by_kind(conn, "headshot")
    live_videos = _assets_by_kind(conn, "live_video")
    audio_demos = _assets_by_kind(conn, "audio_demo")
    repertoire = _asset_by_kind(conn, "repertoire_list")
    rate_card = _asset_by_kind(conn, "rate_card")

    bio_text = _inline_text(bio["path_or_url"]) if bio else None
    headshot_data_uri = _embed_image(headshot["path_or_url"]) if headshot else None
    repertoire_text = _inline_text(repertoire["path_or_url"]) if repertoire else None
    rate_text = _inline_text(rate_card["path_or_url"]) if rate_card else None
    rate_link = (
        rate_card["path_or_url"]
        if rate_card and not rate_text and not is_local_file(rate_card["path_or_url"])
        else None
    )

    def links(assets: list[sqlite3.Row]) -> str:
        items = [
            f'<li><a href="{_esc(a["path_or_url"])}">{_esc(a["name"])}</a></li>'
            for a in assets
            if a["path_or_url"] and not is_local_file(a["path_or_url"])
        ]
        return "\n".join(items)

    video_links = links(live_videos)
    audio_links = links(audio_demos)

    sections = []
    if headshot_data_uri:
        sections.append(
            f'<img class="headshot" src="{headshot_data_uri}" alt="{_esc(artist_name)} headshot">'
        )
    if bio_text:
        sections.append(f"<section><h2>Bio</h2><pre>{_esc(bio_text)}</pre></section>")
    if video_links:
        sections.append(f"<section><h2>Live videos</h2><ul>{video_links}</ul></section>")
    if audio_links:
        sections.append(f"<section><h2>Audio</h2><ul>{audio_links}</ul></section>")
    if repertoire_text:
        sections.append(f"<section><h2>Repertoire</h2><pre>{_esc(repertoire_text)}</pre></section>")
    if rate_text:
        sections.append(f"<section><h2>Rates</h2><pre>{_esc(rate_text)}</pre></section>")
    elif rate_link:
        sections.append(
            f'<section><h2>Rates</h2><p><a href="{_esc(rate_link)}">Rate card</a></p></section>'
        )

    body = "\n".join(sections)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(artist_name)} — Electronic Press Kit</title>
<style>{_STYLE}</style>
</head>
<body>
<h1>{_esc(artist_name)}</h1>
<p class="tagline">vamp till ready</p>
{body}
</body>
</html>
"""


def export_epk(conn: sqlite3.Connection, vamp_home: Path, artist_name: str = "Kaelyn") -> Path:
    """Render + persist the EPK to ``~/.vamp/epk/epk.html`` and return its path."""
    doc = generate_epk_html(conn, artist_name=artist_name)
    out_dir = vamp_home / "epk"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "epk.html"
    out_path.write_text(doc)
    return out_path
