from __future__ import annotations

import tomllib
from pathlib import Path

from engine import __version__ as engine_init_version
from engine.version import ENGINE_VERSION
from mesh_cli.version_info import get_tool_version


def test_engine_version_constant_matches_canonical_accessor() -> None:
    canonical = get_tool_version()
    assert ENGINE_VERSION == canonical
    assert engine_init_version == canonical


def test_pyproject_version_matches_canonical_accessor() -> None:
    pyproject_path = Path("pyproject.toml")
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project_version = str(data["project"]["version"])
    assert project_version == get_tool_version()
