from __future__ import annotations

from pathlib import Path

from vamp import db as vamp_db
from vamp.config import load_config
from vamp.money import floor as floor_service
from vamp.profile import service as profile_service


def _conn(vamp_home: Path):
    return vamp_db.get_connection(load_config(home=vamp_home).db_path)


def test_no_floor_set_returns_none(vamp_home: Path):
    conn = _conn(vamp_home)
    try:
        assert floor_service.get_rate_floor(conn) is None
    finally:
        conn.close()


def test_floor_parses_from_profile(vamp_home: Path):
    conn = _conn(vamp_home)
    try:
        profile_service.set_profile(conn, {"rate_floor": "150"})
        assert floor_service.get_rate_floor(conn) == 150.0
    finally:
        conn.close()


def test_garbage_floor_value_is_ignored(vamp_home: Path):
    conn = _conn(vamp_home)
    try:
        profile_service.set_profile(conn, {"rate_floor": "not-a-number"})
        assert floor_service.get_rate_floor(conn) is None
    finally:
        conn.close()


def test_is_below_floor():
    assert floor_service.is_below_floor(100, 150) is True
    assert floor_service.is_below_floor(150, 150) is False
    assert floor_service.is_below_floor(200, 150) is False
    assert floor_service.is_below_floor(None, 150) is False
    assert floor_service.is_below_floor(100, None) is False
