from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]


def _budget_payload(*, ok: bool) -> dict[str, object]:
    return {
        "schema_version": 2,
        "ok": bool(ok),
        "tolerance_ms": 50,
        "candidates_used": [],
        "checked_steps": [
            {
                "name": "pytest-fast",
                "budget_ms": 20000,
                "tolerance_ms": 50,
                "ratio_limit": 1.25,
                "threshold_ms": 25000,
                "current_ms": 27500,
                "median_ms": 17000,
                "effective_ms": 27500,
                "delta_ms": 2500,
                "ok": bool(ok),
            }
        ],
        "offenders": ([] if ok else [{"name": "pytest-fast", "delta_ms": 2500, "effective_ms": 27500}]),
    }


def test_write_pytest_fast_budget_diagnostic_artifacts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import mesh_cli.verify as verify_mod

    repo_root = tmp_path / "repo"
    artifacts_dir = repo_root / "artifacts"
    artifacts_dir.mkdir(parents=True)

    monkeypatch.setattr(
        verify_mod,
        "_run_pytest_fast_budget_diagnostic",
        lambda **_kwargs: (0, "durations stdout", "durations stderr"),
    )

    verify_mod._write_pytest_fast_budget_diagnostic_artifacts(
        repo_root=repo_root,
        artifacts_dir=artifacts_dir,
        verify_step_budget_payload=_budget_payload(ok=False),
    )

    diag_json_path = artifacts_dir / "pytest_fast_budget_diagnostic.json"
    diag_txt_path = artifacts_dir / "pytest_fast_budget_diagnostic.txt"
    assert diag_json_path.exists()
    assert diag_txt_path.exists()

    data = json.loads(diag_json_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    for key in [
        "step",
        "command_argv",
        "command_line",
        "wall_time_seconds",
        "threshold_ms",
        "current_ms",
        "python_version",
        "diagnostic_command_argv",
        "diagnostic_command_line",
        "diagnostic_returncode",
    ]:
        assert key in data
    assert data["step"] == "pytest-fast"
    assert data["threshold_ms"] == 25000
    assert data["current_ms"] == 27500


def test_is_pytest_fast_budget_offender() -> None:
    import mesh_cli.verify as verify_mod

    assert verify_mod._is_pytest_fast_budget_offender(_budget_payload(ok=False)) is True
    assert verify_mod._is_pytest_fast_budget_offender(_budget_payload(ok=True)) is False

