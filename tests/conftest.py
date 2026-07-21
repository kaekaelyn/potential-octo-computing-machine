from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def vamp_home(tmp_path: Path) -> Path:
    """An isolated ~/.vamp for tests — never touches the real home dir."""
    return tmp_path / ".vamp"
