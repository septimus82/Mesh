from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from mesh_cli import verify as verify_mod

pytestmark = [pytest.mark.fast]


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def _durations_payload(step_ms: dict[str, int]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "total_ms": int(sum(step_ms.values())),
        "steps": [{"name": name, "ok": True, "ms": int(ms)} for name, ms in sorted(step_ms.items())],
    }


def _write_duration(path: Path, step_ms: dict[str, int], *, mtime: int) -> None:
    _write_json(path, _durations_payload(step_ms))
    os.utime(path, (mtime, mtime))


def test_verify_step_budget_guard_no_history_uses_current(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    step_durations_payload = _durations_payload({"step_a": 105})
    baseline_path = tmp_path / "verify_step_budget.json"
    _write_json(
        baseline_path,
        {
            "schema_version": 1,
            "budgets_ms": {"step_a": 100},
            "tolerance_ms": 10,
        },
    )

    code, error, payload = verify_mod._evaluate_verify_step_budget_guard(
        step_durations_payload=step_durations_payload,
        baseline_path=baseline_path,
        update_command="python -c \"noop\"",
        artifacts_dir=artifacts_dir,
    )

    assert code == 0
    assert error == ""
    assert payload["schema_version"] == 2
    assert payload["ok"] is True
    assert payload["tolerance_ms"] == 10
    assert payload["candidates_used"] == []
    checked_steps = payload["checked_steps"]
    assert isinstance(checked_steps, list)
    assert [row["name"] for row in checked_steps] == ["step_a"]
    assert checked_steps[0]["current_ms"] == 105
    assert checked_steps[0]["median_ms"] is None
    assert checked_steps[0]["effective_ms"] == 105
    assert payload["offenders"] == []


def test_verify_step_budget_guard_with_history_uses_max_current_median(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    _write_duration(artifacts_dir / "run_a" / "verify_step_durations.json", {"step_x": 140}, mtime=100)
    _write_duration(artifacts_dir / "run_b" / "verify_step_durations.json", {"step_x": 130}, mtime=101)
    _write_duration(artifacts_dir / "verify_step_durations_20240101.json", {"step_x": 150}, mtime=102)
    step_durations_payload = _durations_payload({"step_x": 100})
    baseline_path = tmp_path / "verify_step_budget.json"
    _write_json(
        baseline_path,
        {
            "schema_version": 1,
            "budgets_ms": {"step_x": 120},
            "tolerance_ms": 5,
        },
    )
    update_command = "python -c \"update\""

    code, error, payload = verify_mod._evaluate_verify_step_budget_guard(
        step_durations_payload=step_durations_payload,
        baseline_path=baseline_path,
        update_command=update_command,
        artifacts_dir=artifacts_dir,
    )

    assert code == 2
    assert "verify slow-step budget exceeded" in error
    assert f"update baseline with: {update_command}" in error
    assert "step_x: budget_ms=120" in error
    assert "tolerance_ms=5" in error
    assert "current_ms=100" in error
    assert "median_ms=140" in error
    assert "effective_ms=140" in error
    assert "delta_ms=15" in error
    assert payload["candidates_used"] == [
        "run_a/verify_step_durations.json",
        "run_b/verify_step_durations.json",
        "verify_step_durations_20240101.json",
    ]
    offenders = payload["offenders"]
    assert isinstance(offenders, list)
    assert [row["name"] for row in offenders] == ["step_x"]
    assert payload["ok"] is False
    checked = payload["checked_steps"][0]
    assert checked["median_ms"] == 140
    assert checked["effective_ms"] == 140
    assert checked["delta_ms"] == 15


def test_verify_step_budget_guard_history_opt_out_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    _write_duration(artifacts_dir / "run_a" / "verify_step_durations.json", {"step_x": 200}, mtime=100)
    step_durations_payload = _durations_payload({"step_x": 100})
    baseline_path = tmp_path / "verify_step_budget.json"
    _write_json(
        baseline_path,
        {
            "schema_version": 1,
            "budgets_ms": {"step_x": 120},
            "tolerance_ms": 5,
        },
    )
    monkeypatch.setenv("MESH_VERIFY_STEP_BUDGET_NO_HISTORY", "1")

    code, error, payload = verify_mod._evaluate_verify_step_budget_guard(
        step_durations_payload=step_durations_payload,
        baseline_path=baseline_path,
        update_command="python -c \"noop\"",
        artifacts_dir=artifacts_dir,
    )

    assert code == 0
    assert error == ""
    assert payload["candidates_used"] == []
    checked = payload["checked_steps"][0]
    assert checked["median_ms"] is None
    assert checked["effective_ms"] == 100


def test_collect_recent_step_durations_selects_most_recent_deterministically(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    _write_duration(artifacts_dir / "a" / "verify_step_durations.json", {"s": 1}, mtime=1)
    _write_duration(artifacts_dir / "b" / "verify_step_durations.json", {"s": 1}, mtime=2)
    _write_duration(artifacts_dir / "c" / "verify_step_durations.json", {"s": 1}, mtime=3)
    _write_duration(artifacts_dir / "d" / "verify_step_durations.json", {"s": 1}, mtime=4)
    _write_duration(artifacts_dir / "e" / "verify_step_durations.json", {"s": 1}, mtime=5)
    _write_duration(artifacts_dir / "verify_step_durations_old.json", {"s": 1}, mtime=6)
    _write_duration(artifacts_dir / "verify_step_durations_new.json", {"s": 1}, mtime=7)

    payloads, used = verify_mod._collect_recent_step_durations(artifacts_dir, limit=5)

    assert len(payloads) == 5
    assert used == [
        "c/verify_step_durations.json",
        "d/verify_step_durations.json",
        "e/verify_step_durations.json",
        "verify_step_durations_new.json",
        "verify_step_durations_old.json",
    ]
