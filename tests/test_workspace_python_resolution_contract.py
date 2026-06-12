from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]


def test_workspace_python_resolution_contract() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    settings_path = repo_root / ".vscode" / "settings.json"
    assert settings_path.exists(), "missing .vscode/settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))

    assert settings.get("python.defaultInterpreterPath") == "${workspaceFolder}/.venv"
    extra_paths = settings.get("python.analysis.extraPaths")
    assert isinstance(extra_paths, list)
    assert "${workspaceFolder}" in extra_paths

    pyright_path = repo_root / "pyrightconfig.json"
    assert pyright_path.exists(), "missing pyrightconfig.json"
    pyright = json.loads(pyright_path.read_text(encoding="utf-8"))

    assert pyright.get("venvPath") == "."
    assert pyright.get("venv") == ".venv"
    include = pyright.get("include")
    assert isinstance(include, list)
    assert "tests" in include
