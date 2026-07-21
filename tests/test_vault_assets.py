from __future__ import annotations

from pathlib import Path

from vamp import db as vamp_db
from vamp.app import create_app
from vamp.config import load_config


def _client(vamp_home: Path):
    config = load_config(home=vamp_home)
    app = create_app(config)
    app.testing = True
    return app.test_client(), config


def test_create_list_toggle_and_delete_asset(vamp_home: Path):
    client, config = _client(vamp_home)

    create = client.post(
        "/vault",
        data={"kind": "bio", "name": "150-word bio", "url": "", "tags": "150-word", "ready": "on"},
    )
    assert create.status_code == 302

    listing = client.get("/vault").get_data(as_text=True)
    assert "150-word bio" in listing
    assert "ready" in listing.lower()

    toggle = client.post("/vault/1/toggle-ready")
    assert toggle.status_code == 302
    listing_after = client.get("/vault").get_data(as_text=True)
    assert "not ready" in listing_after.lower()

    delete = client.post("/vault/1/delete")
    assert delete.status_code == 302
    listing_gone = client.get("/vault").get_data(as_text=True)
    assert "<strong>150-word bio</strong>" not in listing_gone


def test_asset_missing_name_or_kind_is_rejected(vamp_home: Path):
    client, config = _client(vamp_home)

    response = client.post("/vault", data={"kind": "bio", "name": ""})
    assert response.status_code == 302

    conn = vamp_db.get_connection(config.db_path)
    try:
        count = conn.execute("SELECT COUNT(*) AS n FROM assets").fetchone()["n"]
    finally:
        conn.close()
    assert count == 0


def test_url_asset_is_not_treated_as_local_file(vamp_home: Path):
    client, config = _client(vamp_home)
    client.post(
        "/vault",
        data={
            "kind": "live_video",
            "name": "YouTube take",
            "url": "https://youtu.be/abc123",
            "tags": "",
        },
    )

    listing = client.get("/vault").get_data(as_text=True)
    assert "https://youtu.be/abc123" in listing


def test_toggle_missing_asset_404s(vamp_home: Path):
    client, _config = _client(vamp_home)
    response = client.post("/vault/999/toggle-ready")
    assert response.status_code == 404
