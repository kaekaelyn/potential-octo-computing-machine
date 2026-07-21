from __future__ import annotations

from pathlib import Path

from vamp.app import create_app
from vamp.config import load_config


def _client(vamp_home: Path):
    config = load_config(home=vamp_home)
    app = create_app(config)
    app.testing = True
    return app.test_client()


def test_sources_page_lists_default_adzuna_and_usajobs(vamp_home: Path):
    client = _client(vamp_home)

    listing = client.get("/sources").get_data(as_text=True)

    assert "Adzuna" in listing
    assert "USAJOBS" in listing
    assert "enabled" in listing


def test_toggle_disables_and_reenables_a_source(vamp_home: Path):
    client = _client(vamp_home)

    toggle = client.post("/sources/1/toggle")
    assert toggle.status_code == 302

    listing = client.get("/sources").get_data(as_text=True)
    assert "disabled" in listing

    client.post("/sources/1/toggle")
    listing_again = client.get("/sources").get_data(as_text=True)
    assert listing_again.count("disabled") == 0


def test_toggle_missing_source_404s(vamp_home: Path):
    client = _client(vamp_home)
    response = client.post("/sources/999/toggle")
    assert response.status_code == 404


def test_add_rss_source(vamp_home: Path):
    client = _client(vamp_home)

    response = client.post(
        "/sources/add-rss",
        data={"name": "OKC Arts Council", "feed_url": "https://example.org/feed.xml"},
    )
    assert response.status_code == 302

    listing = client.get("/sources").get_data(as_text=True)
    assert "OKC Arts Council" in listing


def test_add_rss_requires_name_and_url(vamp_home: Path):
    client = _client(vamp_home)

    client.post("/sources/add-rss", data={"name": "", "feed_url": ""})

    listing = client.get("/sources").get_data(as_text=True)
    assert "needs a name and a feed URL" in listing


def test_add_page_watch_source(vamp_home: Path):
    client = _client(vamp_home)

    response = client.post(
        "/sources/add-page-watch",
        data={
            "name": "Arts Council Opportunities",
            "url": "https://arts.example.org/opportunities",
            "mode": "diff",
            "interval_hours": "24",
        },
    )
    assert response.status_code == 302

    listing = client.get("/sources").get_data(as_text=True)
    assert "Arts Council Opportunities" in listing


def test_add_page_watch_refuses_blocklisted_domain(vamp_home: Path):
    client = _client(vamp_home)

    client.post(
        "/sources/add-page-watch",
        data={
            "name": "FB group",
            "url": "https://www.facebook.com/groups/okcmusicianscircle/",
            "mode": "diff",
            "interval_hours": "24",
        },
    )

    listing = client.get("/sources").get_data(as_text=True)
    assert "FB group" not in listing
    assert "Couldn" in listing  # "Couldn't add page watcher: ..."


def test_add_page_watch_refuses_interval_under_24h(vamp_home: Path):
    client = _client(vamp_home)

    client.post(
        "/sources/add-page-watch",
        data={
            "name": "Too frequent",
            "url": "https://arts.example.org/opportunities",
            "mode": "diff",
            "interval_hours": "1",
        },
    )

    listing = client.get("/sources").get_data(as_text=True)
    assert "Too frequent" not in listing
