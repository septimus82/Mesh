from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]


def test_ruff_global_ignore_does_not_include_f841() -> None:
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    payload = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    tool = payload.get("tool", {})
    ruff = tool.get("ruff", {})
    lint = ruff.get("lint", {})

    ignore = set()
    for section in (ruff, lint):
        values = section.get("ignore")
        if isinstance(values, list):
            ignore.update(str(value) for value in values)

    assert "F841" not in ignore, "Global Ruff ignore must not include F841"
