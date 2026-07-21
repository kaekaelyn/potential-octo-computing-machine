from __future__ import annotations

from pathlib import Path

from vamp.app import create_app
from vamp.config import load_config


def _client(vamp_home: Path):
    config = load_config(home=vamp_home)
    app = create_app(config)
    app.testing = True
    return app.test_client()


def test_create_list_and_check_patrol_item(vamp_home: Path):
    client = _client(vamp_home)

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
    assert "never checked" in listing

    check = client.post("/patrol/1/check")
    assert check.status_code == 302

    listing_after = client.get("/patrol").get_data(as_text=True)
    assert "never checked" not in listing_after
    assert "checked-today" in listing_after


def test_edit_patrol_item(vamp_home: Path):
    client = _client(vamp_home)
    client.post("/patrol", data={"name": "Old name", "url": "", "notes": ""})

    client.post("/patrol/1/edit", data={"name": "New name", "url": "", "notes": "updated"})

    listing = client.get("/patrol").get_data(as_text=True)
    assert "New name" in listing
    assert "Old name" not in listing


def test_delete_patrol_item(vamp_home: Path):
    client = _client(vamp_home)
    client.post("/patrol", data={"name": "Temporary", "url": "", "notes": ""})

    client.post("/patrol/1/delete")

    listing = client.get("/patrol").get_data(as_text=True)
    assert "Temporary" not in listing
    assert "No patrol items yet" in listing


def test_check_missing_patrol_item_404s(vamp_home: Path):
    client = _client(vamp_home)
    response = client.post("/patrol/999/check")
    assert response.status_code == 404
