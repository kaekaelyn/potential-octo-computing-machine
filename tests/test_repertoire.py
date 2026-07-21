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


def test_add_item_tags_by_occasion_and_shows_up_in_listing(vamp_home: Path):
    client, _config = _client(vamp_home)

    response = client.post(
        "/vault/repertoire",
        data={
            "title": "Fly Me to the Moon",
            "artist": "Frank Sinatra",
            "occasions": ["jazz", "cocktail"],
            "notes": "",
        },
    )
    assert response.status_code == 302

    listing = client.get("/vault/repertoire").get_data(as_text=True)
    assert "Fly Me to the Moon" in listing
    assert "jazz" in listing
    assert "cocktail" in listing


def test_adding_items_syncs_the_vault_repertoire_list_asset(vamp_home: Path):
    client, config = _client(vamp_home)

    client.post(
        "/vault/repertoire",
        data={"title": "Ave Maria", "artist": "", "occasions": ["worship"], "notes": ""},
    )

    conn = vamp_db.get_connection(config.db_path)
    try:
        asset = conn.execute("SELECT * FROM assets WHERE kind = 'repertoire_list'").fetchone()
    finally:
        conn.close()
    assert asset is not None
    assert asset["ready"] == 1
    assert "worship" in asset["tags"]
    compiled = Path(asset["path_or_url"]).read_text()
    assert "Ave Maria" in compiled
    assert "Worship:" in compiled


def test_deleting_all_items_marks_the_asset_not_ready(vamp_home: Path):
    client, config = _client(vamp_home)
    client.post(
        "/vault/repertoire",
        data={"title": "Solo Improv", "artist": "", "occasions": ["improv"], "notes": ""},
    )

    client.post("/vault/repertoire/1/delete")

    conn = vamp_db.get_connection(config.db_path)
    try:
        asset = conn.execute("SELECT * FROM assets WHERE kind = 'repertoire_list'").fetchone()
    finally:
        conn.close()
    assert asset["ready"] == 0
