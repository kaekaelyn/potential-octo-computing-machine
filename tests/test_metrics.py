from __future__ import annotations

from pathlib import Path

from vamp import db as vamp_db
from vamp.app import create_app
from vamp.config import load_config
from vamp.gigs import pipeline as gigs_pipeline
from vamp.metrics import service
from vamp.prospects import pipeline as prospects_pipeline


def _conn(vamp_home: Path):
    return vamp_db.get_connection(load_config(home=vamp_home).db_path)


def _client(vamp_home: Path):
    config = load_config(home=vamp_home)
    app = create_app(config)
    app.testing = True
    return app.test_client(), config


def test_pipeline_funnel_buckets_by_current_status(vamp_home: Path):
    conn = _conn(vamp_home)
    try:
        prospects_pipeline.create_prospect(conn, {"name": "Identified Only", "category": "hotel"})
        contacted = prospects_pipeline.create_prospect(
            conn, {"name": "Contacted", "category": "hotel"}
        )
        prospects_pipeline.set_status(conn, contacted, "contacted")
        conversing = prospects_pipeline.create_prospect(
            conn, {"name": "In Conversation", "category": "hotel"}
        )
        prospects_pipeline.set_status(conn, conversing, "in_conversation")
        booked = prospects_pipeline.create_prospect(conn, {"name": "Booked", "category": "hotel"})
        prospects_pipeline.set_status(conn, booked, "booked")

        rows = {r["category"]: r for r in service.pipeline_funnel(conn)}
        hotel = rows["hotel"]
        # identified doesn't count as pitched; contacted/in_conversation/booked all do.
        assert hotel["pitched"] == 3
        assert hotel["responded"] == 2  # in_conversation + booked
        assert hotel["booked"] == 1
    finally:
        conn.close()


def test_source_conversion_counts_leads_and_linked_gigs(vamp_home: Path):
    conn = _conn(vamp_home)
    try:
        source_id = conn.execute(
            "INSERT INTO sources (kind, name, enabled) VALUES ('rss', 'Test Feed', 1)"
        ).lastrowid
        lead_with_gig = conn.execute(
            "INSERT INTO leads (source_id, kind, dedupe_hash, url_hash, title, state) "
            "VALUES (?, 'gig', 'a', 'a', 'Lead A', 'inbox')",
            (source_id,),
        ).lastrowid
        conn.execute(
            "INSERT INTO leads (source_id, kind, dedupe_hash, url_hash, title, state) "
            "VALUES (?, 'gig', 'b', 'b', 'Lead B', 'inbox')",
            (source_id,),
        )
        conn.commit()
        gigs_pipeline.create_gig(conn, {"lead_id": lead_with_gig, "venue": "Vast"})

        rows = {r["source_name"]: r for r in service.source_conversion(conn)}
        row = rows["Test Feed"]
        assert row["leads"] == 2
        assert row["gigs"] == 1
    finally:
        conn.close()


def test_metrics_page_renders(vamp_home: Path):
    # A fresh app already has M4's seeded prospects/sources, so this just
    # checks the page renders with real data rather than asserting "empty".
    client, _config = _client(vamp_home)
    body = client.get("/metrics").get_data(as_text=True)
    assert "Metrics" in body
    assert "Pitched" in body
    assert "Source" in body
