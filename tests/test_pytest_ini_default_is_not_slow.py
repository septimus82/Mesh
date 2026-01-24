from __future__ import annotations

import configparser
import shlex
from pathlib import Path

import pytest

pytestmark = pytest.mark.fast


def test_pytest_ini_default_is_not_slow() -> None:
    config = configparser.ConfigParser()
    pytest_ini = Path(__file__).resolve().parents[1] / "pytest.ini"
    config.read(pytest_ini)

    addopts = config["pytest"].get("addopts", "")
    opts = shlex.split(addopts)

    assert "-m" in opts, "pytest.ini addopts must include -m filter"
    expr = opts[opts.index("-m") + 1]
    assert expr == "not slow and not e2e"
