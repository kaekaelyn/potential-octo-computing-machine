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


def _item_id(config, name: str) -> int:
    # M4 seeds a starter patrol list, so a freshly created item is not id=1.
    conn = vamp_db.get_connection(config.db_path)
    try:
        return conn.execute("SELECT id FROM patrol_items WHERE name = ?", (name,)).fetchone()["id"]
    finally:
        conn.close()


def test_create_list_and_check_patrol_item(vamp_home: Path):
    client, config = _client(vamp_home)

    create = client.post(
        "/patrol",
        data={
            "name": "OKC Musicians Circle",
            "url": "https://www.facebook.com/groups/okcmusicianscircle/",
            "notes": "Gigs get posted here a few times a week.",
        },
    )
    assert create.status_code == 302

    listing = client.get("/patrol").get_data(as_text=True)
    assert "OKC Musicians Circle" in listing

    item_id = _item_id(config, "OKC Musicians Circle")
    check = client.post(f"/patrol/{item_id}/check")
    assert check.status_code == 302

    listing_after = client.get("/patrol").get_data(as_text=True)
    assert "checked-today" in listing_after


def test_edit_patrol_item(vamp_home: Path):
    client, config = _client(vamp_home)
    client.post("/patrol", data={"name": "Old name", "url": "", "notes": ""})

    item_id = _item_id(config, "Old name")
    client.post(f"/patrol/{item_id}/edit", data={"name": "New name", "url": "", "notes": "updated"})

    listing = client.get("/patrol").get_data(as_text=True)
    assert "New name" in listing
    assert "Old name" not in listing


def test_delete_patrol_item(vamp_home: Path):
    client, config = _client(vamp_home)
    client.post("/patrol", data={"name": "Temporary", "url": "", "notes": ""})

    item_id = _item_id(config, "Temporary")
    client.post(f"/patrol/{item_id}/delete")

    listing = client.get("/patrol").get_data(as_text=True)
    assert "Temporary" not in listing


def test_check_missing_patrol_item_404s(vamp_home: Path):
    client, _config = _client(vamp_home)
    response = client.post("/patrol/999/check")
    assert response.status_code == 404
