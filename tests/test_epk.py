from __future__ import annotations

from pathlib import Path

from vamp import db as vamp_db
from vamp.config import load_config
from vamp.vault import assets as assets_service
from vamp.vault.epk import epk_readiness, export_epk, generate_epk_html


def _conn(vamp_home: Path):
    config = load_config(home=vamp_home)
    return vamp_db.get_connection(config.db_path), config


def test_epk_is_self_contained_and_omits_missing_sections(vamp_home: Path):
    conn, _config = _conn(vamp_home)

    html = generate_epk_html(conn, artist_name="Kaelyn")

    assert "<!doctype html>" in html
    assert "Kaelyn" in html
    assert "http://" not in html and "https://" not in html  # nothing to link yet
    assert "<section>" not in html  # no ready assets at all


def test_epk_embeds_local_image_headshot_as_data_uri(vamp_home: Path, tmp_path: Path):
    conn, config = _conn(vamp_home)
    image_bytes = bytes.fromhex("89504e470d0a1a0a")  # PNG magic bytes, not a full image
    assets_service.create_asset(
        conn,
        config.home,
        kind="headshot",
        name="Headshot",
        file_name="headshot.png",
        file_bytes=image_bytes,
        ready=True,
    )

    html = generate_epk_html(conn)

    assert "data:image/png;base64," in html


def test_epk_inlines_local_text_bio_and_links_remote_video(vamp_home: Path):
    conn, config = _conn(vamp_home)
    assets_service.create_asset(
        conn,
        config.home,
        kind="bio",
        name="Bio",
        file_name="bio.txt",
        file_bytes=b"Kaelyn is a pianist based in OKC.",
        ready=True,
    )
    assets_service.create_asset(
        conn,
        config.home,
        kind="live_video",
        name="Solo improv",
        url="https://youtu.be/abc123",
        ready=True,
    )

    html = generate_epk_html(conn)

    assert "Kaelyn is a pianist based in OKC." in html
    assert 'href="https://youtu.be/abc123"' in html


def test_export_epk_writes_to_disk(vamp_home: Path):
    conn, config = _conn(vamp_home)

    out_path = export_epk(conn, config.home)

    assert out_path.exists()
    assert out_path.name == "epk.html"
    assert "<!doctype html>" in out_path.read_text()


def test_epk_readiness_reflects_vault_state(vamp_home: Path):
    conn, config = _conn(vamp_home)

    assert epk_readiness(conn)["core_ready"] is False

    assets_service.create_asset(conn, config.home, kind="bio", name="Bio", ready=True)
    assets_service.create_asset(conn, config.home, kind="headshot", name="Headshot", ready=True)
    assets_service.create_asset(conn, config.home, kind="live_video", name="Video", ready=True)

    readiness = epk_readiness(conn)
    assert readiness["core_ready"] is True
