from __future__ import annotations

import types

import pytest

import tooling.pytest_full as pytest_full

pytestmark = pytest.mark.fast


def test_tier2_runs_full_suite_flag(monkeypatch) -> None:
    captured: dict[str, list[str]] = {}

    def fake_run(cmd, **_kwargs):  # noqa: ANN001
        captured["cmd"] = cmd
        return types.SimpleNamespace(returncode=0)

    monkeypatch.setattr(pytest_full.subprocess, "run", fake_run)

    rc = pytest_full.main([])
    assert rc == 0
    cmd = captured["cmd"]
    pytest_idx = cmd.index("pytest")
    assert "-m" not in cmd[pytest_idx + 1 :], "pytest_full must not filter markers"
    assert "-o" in cmd and "addopts=" in cmd, "pytest_full should clear ini addopts"
