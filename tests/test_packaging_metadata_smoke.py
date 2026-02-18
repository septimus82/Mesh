from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]


def test_pyproject_packaging_metadata_smoke() -> None:
    pyproject_path = Path("pyproject.toml")
    assert pyproject_path.exists()
    data = pyproject_path.read_text(encoding="utf-8")
    parsed = __import__("tomllib").loads(data)

    project = parsed.get("project", {})
    assert isinstance(project, dict)
    assert isinstance(project.get("name"), str) and project["name"]
    assert isinstance(project.get("version"), str) and project["version"]
    assert isinstance(project.get("requires-python"), str) and project["requires-python"]
    assert "license" in project

    deps = project.get("dependencies")
    assert isinstance(deps, list)
    dep_text = " ".join(str(dep) for dep in deps)
    assert "arcade>=" in dep_text
    assert ">=3" in dep_text
    assert "<4" in dep_text

    scripts = project.get("scripts")
    assert isinstance(scripts, dict)
    assert isinstance(scripts.get("mesh"), str) and scripts["mesh"]
