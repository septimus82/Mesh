from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

pytestmark = pytest.mark.fast


def test_dev_extra_pins_mypy_and_pygbag() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    dev_deps = pyproject["project"]["optional-dependencies"]["dev"]

    assert "mypy==1.19.1" in dev_deps
    assert "pygbag==0.9.3" in dev_deps


def test_pre_commit_mypy_mirror_is_aligned_to_dev_pin() -> None:
    text = Path(".pre-commit-config.yaml").read_text(encoding="utf-8")

    assert "repo: https://github.com/pre-commit/mirrors-mypy" in text
    assert "rev: v1.19.1" in text
