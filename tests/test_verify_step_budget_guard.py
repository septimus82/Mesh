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
    assert checked_steps[0]["ratio_limit"] == pytest.approx(1.25)
    assert checked_steps[0]["threshold_ms"] == 125
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
            "ratio_limits": {"step_x": 1.0},
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
    assert "ratio_limit=1.00" in error
    assert "threshold_ms=125" in error
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
    assert checked["ratio_limit"] == pytest.approx(1.0)
    assert checked["threshold_ms"] == 125
    assert checked["median_ms"] == 140
    assert checked["effective_ms"] == 140
    assert checked["delta_ms"] == 15


def test_verify_step_budget_guard_passes_when_over_tolerance_but_under_ratio(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    step_durations_payload = _durations_payload({"step_a": 120})
    baseline_path = tmp_path / "verify_step_budget.json"
    _write_json(
        baseline_path,
        {
            "schema_version": 2,
            "budgets_ms": {"step_a": 100},
            "ratio_limits": {"step_a": 1.25},
            "tolerance_ms": 5,
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
    checked = payload["checked_steps"][0]
    assert checked["ratio_limit"] == pytest.approx(1.25)
    assert checked["threshold_ms"] == 125
    assert checked["effective_ms"] == 120
    assert checked["ok"] is True


def test_verify_step_budget_guard_passes_when_over_ratio_but_under_tolerance(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    step_durations_payload = _durations_payload({"step_a": 120})
    baseline_path = tmp_path / "verify_step_budget.json"
    _write_json(
        baseline_path,
        {
            "schema_version": 2,
            "budgets_ms": {"step_a": 100},
            "ratio_limits": {"step_a": 1.05},
            "tolerance_ms": 30,
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
    checked = payload["checked_steps"][0]
    assert checked["ratio_limit"] == pytest.approx(1.05)
    assert checked["threshold_ms"] == 130
    assert checked["effective_ms"] == 120
    assert checked["ok"] is True


def test_verify_step_budget_guard_fails_when_exceeding_hybrid_threshold(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    step_durations_payload = _durations_payload({"step_a": 131})
    baseline_path = tmp_path / "verify_step_budget.json"
    _write_json(
        baseline_path,
        {
            "schema_version": 2,
            "budgets_ms": {"step_a": 100},
            "ratio_limits": {"step_a": 1.10},
            "tolerance_ms": 20,
        },
    )

    code, error, payload = verify_mod._evaluate_verify_step_budget_guard(
        step_durations_payload=step_durations_payload,
        baseline_path=baseline_path,
        update_command="python -c \"noop\"",
        artifacts_dir=artifacts_dir,
    )

    assert code == 2
    assert "verify slow-step budget exceeded" in error
    assert "step_a: budget_ms=100" in error
    assert "threshold_ms=120" in error
    assert "effective_ms=131" in error
    assert "delta_ms=11" in error
    assert payload["ok"] is False


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


def test_archive_verify_step_durations_artifact_rolls_history_forward_deterministically(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    current_path = artifacts_dir / "verify_step_durations.json"
    _write_json(current_path, _durations_payload({"verify-demo": 100}))

    first = verify_mod._archive_verify_step_durations_artifact(artifacts_dir)
    assert first == artifacts_dir / "verify_step_history" / "verify_step_durations_0001.json"
    assert first.is_file()

    _write_json(current_path, _durations_payload({"verify-demo": 200}))
    second = verify_mod._archive_verify_step_durations_artifact(artifacts_dir)
    assert second == artifacts_dir / "verify_step_history" / "verify_step_durations_0002.json"
    assert second.is_file()

    first_payload = json.loads(first.read_text(encoding="utf-8"))
    second_payload = json.loads(second.read_text(encoding="utf-8"))
    assert first_payload["steps"][0]["ms"] == 100
    assert second_payload["steps"][0]["ms"] == 200


def test_verify_step_budget_guard_uses_archived_history_for_median(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    history_dir = artifacts_dir / "verify_step_history"
    history_dir.mkdir(parents=True, exist_ok=True)
    _write_duration(history_dir / "verify_step_durations_0001.json", {"web-smoke": 10000}, mtime=100)
    _write_duration(history_dir / "verify_step_durations_0002.json", {"web-smoke": 12000}, mtime=101)
    _write_duration(history_dir / "verify_step_durations_0003.json", {"web-smoke": 11000}, mtime=102)
    _write_duration(artifacts_dir / "verify_step_durations.json", {"web-smoke": 11500}, mtime=103)
    step_durations_payload = _durations_payload({"web-smoke": 11500})
    baseline_path = tmp_path / "verify_step_budget.json"
    _write_json(
        baseline_path,
        {
            "schema_version": 2,
            "budgets_ms": {"web-smoke": 10901},
            "ratio_limits": {"web-smoke": 1.25},
            "tolerance_ms": 50,
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
    assert payload["candidates_used"] == [
        "verify_step_history/verify_step_durations_0001.json",
        "verify_step_history/verify_step_durations_0002.json",
        "verify_step_history/verify_step_durations_0003.json",
    ]
    checked = payload["checked_steps"][0]
    assert checked["name"] == "web-smoke"
    assert checked["median_ms"] == 11000
    assert checked["effective_ms"] == 11500


def test_verify_step_budget_guard_checked_steps_sorted_deterministically(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    step_durations_payload = _durations_payload({"step_b": 160, "step_a": 170})
    baseline_path = tmp_path / "verify_step_budget.json"
    _write_json(
        baseline_path,
        {
            "schema_version": 2,
            "budgets_ms": {"step_b": 100, "step_a": 100},
            "ratio_limits": {"step_b": 1.1, "step_a": 1.2},
            "tolerance_ms": 5,
        },
    )
    code, _error, payload = verify_mod._evaluate_verify_step_budget_guard(
        step_durations_payload=step_durations_payload,
        baseline_path=baseline_path,
        update_command="python -c \"noop\"",
        artifacts_dir=artifacts_dir,
    )
    assert code == 2
    checked_steps = payload["checked_steps"]
    assert [row["name"] for row in checked_steps] == ["step_a", "step_b"]


def test_verify_step_budget_guard_verify_demo_near_miss_passes_without_history(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    step_durations_payload = _durations_payload({"verify-demo": 38900})
    baseline_path = tmp_path / "verify_step_budget.json"
    _write_json(
        baseline_path,
        {
            "schema_version": 2,
            "budgets_ms": {"verify-demo": 30979},
            "ratio_limits": {"verify-demo": 1.25},
            "tolerance_ms": 50,
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
    checked = payload["checked_steps"][0]
    assert checked["name"] == "verify-demo"
    assert checked["median_ms"] is None
    assert checked["tolerance_ms"] == 300
    assert checked["threshold_ms"] == 38973
    assert checked["effective_ms"] == 38900
    assert checked["ok"] is True


def test_verify_step_budget_guard_verify_demo_big_miss_still_fails_without_history(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    step_durations_payload = _durations_payload({"verify-demo": 39250})
    baseline_path = tmp_path / "verify_step_budget.json"
    _write_json(
        baseline_path,
        {
            "schema_version": 2,
            "budgets_ms": {"verify-demo": 30979},
            "ratio_limits": {"verify-demo": 1.25},
            "tolerance_ms": 50,
        },
    )

    code, error, payload = verify_mod._evaluate_verify_step_budget_guard(
        step_durations_payload=step_durations_payload,
        baseline_path=baseline_path,
        update_command="python -c \"noop\"",
        artifacts_dir=artifacts_dir,
    )

    assert code == 2
    assert "verify-demo: budget_ms=30979" in error
    checked = payload["checked_steps"][0]
    assert checked["name"] == "verify-demo"
    assert checked["median_ms"] is None
    assert checked["tolerance_ms"] == 300
    assert checked["threshold_ms"] == 38973
    assert checked["effective_ms"] == 39250
    assert checked["ok"] is False


def test_verify_step_budget_guard_player_package_near_miss_passes_without_history(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    step_durations_payload = _durations_payload({"player-package-gate": 4054})
    baseline_path = tmp_path / "verify_step_budget.json"
    _write_json(
        baseline_path,
        {
            "schema_version": 2,
            "budgets_ms": {"player-package-gate": 2723},
            "ratio_limits": {"player-package-gate": 1.25},
            "tolerance_ms": 50,
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
    checked = payload["checked_steps"][0]
    assert checked["name"] == "player-package-gate"
    assert checked["median_ms"] is None
    assert checked["tolerance_ms"] == 750
    assert checked["threshold_ms"] == 4103
    assert checked["effective_ms"] == 4054
    assert checked["ok"] is True


def test_verify_step_budget_guard_player_package_big_miss_still_fails_without_history(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    step_durations_payload = _durations_payload({"player-package-gate": 4200})
    baseline_path = tmp_path / "verify_step_budget.json"
    _write_json(
        baseline_path,
        {
            "schema_version": 2,
            "budgets_ms": {"player-package-gate": 2723},
            "ratio_limits": {"player-package-gate": 1.25},
            "tolerance_ms": 50,
        },
    )

    code, error, payload = verify_mod._evaluate_verify_step_budget_guard(
        step_durations_payload=step_durations_payload,
        baseline_path=baseline_path,
        update_command="python -c \"noop\"",
        artifacts_dir=artifacts_dir,
    )

    assert code == 2
    assert "player-package-gate: budget_ms=2723" in error
    checked = payload["checked_steps"][0]
    assert checked["name"] == "player-package-gate"
    assert checked["median_ms"] is None
    assert checked["tolerance_ms"] == 750
    assert checked["threshold_ms"] == 4103
    assert checked["effective_ms"] == 4200
    assert checked["ok"] is False


def test_verify_step_budget_guard_web_smoke_near_miss_passes_without_history(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    step_durations_payload = _durations_payload({"web-smoke": 14159})
    baseline_path = tmp_path / "verify_step_budget.json"
    _write_json(
        baseline_path,
        {
            "schema_version": 2,
            "budgets_ms": {"web-smoke": 10901},
            "ratio_limits": {"web-smoke": 1.25},
            "tolerance_ms": 50,
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
    checked = payload["checked_steps"][0]
    assert checked["name"] == "web-smoke"
    assert checked["median_ms"] is None
    assert checked["tolerance_ms"] == 650
    assert checked["threshold_ms"] == 14226
    assert checked["effective_ms"] == 14159
    assert checked["ok"] is True


def test_verify_step_budget_guard_web_smoke_big_miss_still_fails_without_history(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    step_durations_payload = _durations_payload({"web-smoke": 14350})
    baseline_path = tmp_path / "verify_step_budget.json"
    _write_json(
        baseline_path,
        {
            "schema_version": 2,
            "budgets_ms": {"web-smoke": 10901},
            "ratio_limits": {"web-smoke": 1.25},
            "tolerance_ms": 50,
        },
    )

    code, error, payload = verify_mod._evaluate_verify_step_budget_guard(
        step_durations_payload=step_durations_payload,
        baseline_path=baseline_path,
        update_command="python -c \"noop\"",
        artifacts_dir=artifacts_dir,
    )

    assert code == 2
    assert "web-smoke: budget_ms=10901" in error
    checked = payload["checked_steps"][0]
    assert checked["name"] == "web-smoke"
    assert checked["median_ms"] is None
    assert checked["tolerance_ms"] == 650
    assert checked["threshold_ms"] == 14226
    assert checked["effective_ms"] == 14350
    assert checked["ok"] is False
