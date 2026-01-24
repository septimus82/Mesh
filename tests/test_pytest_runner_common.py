from __future__ import annotations

import pytest

from tooling.pytest_runner_common import (
    build_pytest_args,
    build_pytest_env,
    format_xdist,
)

pytestmark = pytest.mark.fast


def test_build_pytest_env_strips_addopts() -> None:
    env = {"PYTEST_ADDOPTS": "-m fast", "OTHER": "1"}
    result = build_pytest_env(env)
    assert "PYTEST_ADDOPTS" not in result
    assert result["OTHER"] == "1"


def test_build_pytest_args_includes_addopts_prefix() -> None:
    args = build_pytest_args(["-q", "-m", "fast"])
    assert args[:2] == ["-o", "addopts="]


@pytest.mark.parametrize(
    ("enabled", "workers", "expected"),
    [
        (True, None, "True (workers=auto)"),
        (True, 4, "True (workers=4)"),
        (False, None, "False"),
    ],
)
def test_format_xdist(enabled: bool, workers: int | None, expected: str) -> None:
    assert format_xdist(enabled, workers) == expected
