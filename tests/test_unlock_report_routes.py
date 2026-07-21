from __future__ import annotations

from pathlib import Path

from vamp import db as vamp_db
from vamp.app import create_app
from vamp.capture.parser import ParsedLead
from vamp.config import load_config
from vamp.leads import service as leads_service


def _client(vamp_home: Path):
    config = load_config(home=vamp_home)
    app = create_app(config)
    app.testing = True
    return app.test_client(), config


def test_unlock_report_page_shows_top_unlock(vamp_home: Path):
    client, config = _client(vamp_home)
    conn = vamp_db.get_connection(config.db_path)
    try:
        leads_service.create_lead(
            conn,
            ParsedLead(
                title="A", description="Please send a headshot.", pay_kind="flat", pay_min=100
            ),
        )
        leads_service.create_lead(
            conn,
            ParsedLead(
                title="B", description="Please send a headshot.", pay_kind="flat", pay_min=100
            ),
        )
    finally:
        conn.close()

    body = client.get("/vault/unlock").get_data(as_text=True)

    assert "headshot" in body
    assert "unlocks 2" in body


def test_unlock_report_empty_state(vamp_home: Path):
    client, _config = _client(vamp_home)

    body = client.get("/vault/unlock").get_data(as_text=True)

    assert "No open leads" in body
