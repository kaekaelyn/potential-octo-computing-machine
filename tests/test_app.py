from __future__ import annotations

from pathlib import Path

from vamp.app import create_app
from vamp.config import load_config


def _client(vamp_home: Path):
    config = load_config(home=vamp_home)
    app = create_app(config)
    app.testing = True
    return app.test_client()


def test_dashboard_serves_200_with_counts(vamp_home: Path):
    client = _client(vamp_home)

    response = client.get("/")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Vamp" in body
    assert "Sources" in body


def test_healthz(vamp_home: Path):
    client = _client(vamp_home)

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}
