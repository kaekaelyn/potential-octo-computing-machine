from __future__ import annotations

from pathlib import Path

from scripts.check_pure_python_deps import find_compiled_deps

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_requirements_txt_has_no_known_compiled_packages():
    assert find_compiled_deps(REPO_ROOT / "requirements.txt") == []


def test_detects_a_known_compiled_package(tmp_path: Path):
    bad_requirements = tmp_path / "requirements.txt"
    bad_requirements.write_text("Flask==3.1.3\npydantic==2.9.0\n")

    assert find_compiled_deps(bad_requirements) == ["pydantic"]
