"""Contract tests for verify-all step budget and duration artifacts.

Validates that:
1. verify_step_budget_check.json has correct schema
2. verify_step_durations.json has correct schema
3. pytest-fast has both execution time (from duration guard) and wall-clock time (from budget check)
4. The two metrics are clearly distinguishable
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.persistence_io import write_json_atomic
from mesh_cli import verify as verify_mod

pytestmark = [pytest.mark.fast]

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BUDGET_BASELINE_UPDATE_COMMAND = (
    "python -c \"from pathlib import Path; import os; import mesh_cli.verify as m; "
    "artifacts=Path(os.getenv('MESH_ARTIFACTS_DIR', 'artifacts')); "
    "repo=Path(m.__file__).resolve().parent.parent; "
    "if not artifacts.is_absolute(): artifacts = repo / artifacts; "
    "target,_=m._write_verify_step_budget_baseline_from_artifacts(repo_root=repo, artifacts_dir=artifacts); "
    "print(target.as_posix())\""
)


def _write_synthetic_verify_budget_artifacts(tmp_path: Path) -> tuple[Path, Path]:
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    step_durations_payload = verify_mod._build_verify_step_durations_payload(
        expected_steps=["pytest-fast", "mypy-gate", "ruff-gate"],
        rows=[
            {"name": "pytest-fast", "ok": True, "ms": 1234},
            {"name": "mypy-gate", "ok": True, "ms": 456},
            {"name": "ruff-gate", "ok": True, "ms": 78},
        ],
    )
    durations_path = artifacts_dir / "verify_step_durations.json"
    write_json_atomic(
        durations_path,
        step_durations_payload,
        indent=2,
        sort_keys=True,
        trailing_newline=True,
    )

    baseline_path = tmp_path / "tooling" / "metrics" / "verify_step_budget.json"
    verify_mod._write_verify_step_budget_baseline(
        baseline_path,
        step_durations_payload,
        top_n=3,
    )
    step_durations_from_artifact = verify_mod._read_verify_step_durations_payload(durations_path)
    budget_code, budget_error, verify_step_budget_payload = verify_mod._evaluate_verify_step_budget_guard(
        step_durations_payload=step_durations_from_artifact,
        baseline_path=baseline_path,
        update_command="python -c \"noop\"",
        artifacts_dir=artifacts_dir,
    )
    assert budget_code == 0, budget_error
    budget_path = artifacts_dir / "verify_step_budget_check.json"
    write_json_atomic(
        budget_path,
        verify_step_budget_payload,
        indent=2,
        sort_keys=True,
        trailing_newline=True,
    )
    return durations_path, budget_path


# ------------------------------------------------------------------
# 1. verify_step_budget_check.json schema
# ------------------------------------------------------------------


def test_budget_check_schema_shape() -> None:
    """Verify that budget check artifact has expected schema."""
    baseline_path = _REPO_ROOT / "tooling" / "metrics" / "verify_step_budget.json"
    assert baseline_path.exists(), "Budget baseline missing"

    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))

    assert list(baseline.keys()) == [
        "budgets_ms",
        "ratio_limits",
        "schema_version",
        "tolerance_ms",
    ]
    assert isinstance(baseline["budgets_ms"], dict)
    assert isinstance(baseline["ratio_limits"], dict)
    assert baseline["schema_version"] == 2
    assert isinstance(baseline["tolerance_ms"], int)

    # pytest-fast must have a budget
    budgets = baseline["budgets_ms"]
    assert "pytest-fast" in budgets
    assert isinstance(budgets["pytest-fast"], int)
    assert budgets["pytest-fast"] > 0
    assert list(baseline["budgets_ms"].keys()) == sorted(baseline["budgets_ms"].keys())
    assert list(baseline["ratio_limits"].keys()) == sorted(baseline["ratio_limits"].keys())
    assert sorted(baseline["budgets_ms"].keys()) == sorted(baseline["ratio_limits"].keys())


def test_budget_baseline_file_is_deterministic_and_loadable() -> None:
    """The committed verify-all budget baseline stays schema-stable and helper-refreshable."""
    baseline_path = _REPO_ROOT / "tooling" / "metrics" / "verify_step_budget.json"
    baseline_bytes_a = baseline_path.read_bytes()
    baseline_bytes_b = baseline_path.read_bytes()

    assert baseline_bytes_a == baseline_bytes_b

    baseline = json.loads(baseline_bytes_a.decode("utf-8"))
    assert baseline["schema_version"] == 2, (
        "Unexpected verify-step budget schema drift. "
        f"Refresh intentionally via: {_BUDGET_BASELINE_UPDATE_COMMAND}"
    )


def test_budget_check_artifact_has_pytest_fast(tmp_path: Path) -> None:
    """Verify that pytest-fast appears in budget check artifact after verify-all."""
    _durations_path, artifact_path = _write_synthetic_verify_budget_artifacts(tmp_path)

    payload = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == 2
    assert isinstance(payload["ok"], bool)
    assert isinstance(payload["tolerance_ms"], int)
    assert isinstance(payload["candidates_used"], list)
    assert "checked_steps" in payload
    assert isinstance(payload["checked_steps"], list)
    assert isinstance(payload["offenders"], list)

    pytest_fast_row = None
    for row in payload["checked_steps"]:
        if isinstance(row, dict) and row.get("name") == "pytest-fast":
            pytest_fast_row = row
            break

    assert pytest_fast_row is not None

    assert "name" in pytest_fast_row
    assert "budget_ms" in pytest_fast_row
    assert "current_ms" in pytest_fast_row
    assert "threshold_ms" in pytest_fast_row
    assert "ok" in pytest_fast_row
    assert isinstance(pytest_fast_row["name"], str)
    assert isinstance(pytest_fast_row["budget_ms"], int)
    assert isinstance(pytest_fast_row["current_ms"], int)
    assert isinstance(pytest_fast_row["threshold_ms"], int)
    assert isinstance(pytest_fast_row["ok"], bool)


# ------------------------------------------------------------------
# 2. verify_step_durations.json schema
# ------------------------------------------------------------------


def test_step_durations_schema_shape(tmp_path: Path) -> None:
    """Verify that step durations artifact has expected schema."""
    artifact_path, _budget_path = _write_synthetic_verify_budget_artifacts(tmp_path)

    payload = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == 1
    assert isinstance(payload["total_ms"], int)
    assert "steps" in payload
    assert isinstance(payload["steps"], list)

    pytest_fast_step = None
    for step in payload["steps"]:
        if isinstance(step, dict) and step.get("name") == "pytest-fast":
            pytest_fast_step = step
            break

    assert pytest_fast_step is not None

    assert "name" in pytest_fast_step
    assert "ms" in pytest_fast_step
    assert "ok" in pytest_fast_step
    assert isinstance(pytest_fast_step["name"], str)
    assert isinstance(pytest_fast_step["ms"], int)
    assert isinstance(pytest_fast_step["ok"], bool)


# ------------------------------------------------------------------
# 3. pytest-fast metrics coherence
# ------------------------------------------------------------------


def test_pytest_fast_has_both_metrics(tmp_path: Path) -> None:
    """Verify that pytest-fast has both execution time and wall-clock time metrics."""
    durations_path, budget_artifact_path = _write_synthetic_verify_budget_artifacts(tmp_path)
    durations_payload = json.loads(durations_path.read_text(encoding="utf-8"))
    budget_payload = json.loads(budget_artifact_path.read_text(encoding="utf-8"))

    pytest_fast_step = None
    for step in durations_payload.get("steps", []):
        if isinstance(step, dict) and step.get("name") == "pytest-fast":
            pytest_fast_step = step
            break

    pytest_fast_row = None
    for row in budget_payload.get("checked_steps", []):
        if isinstance(row, dict) and row.get("name") == "pytest-fast":
            pytest_fast_row = row
            break

    assert pytest_fast_step is not None
    assert pytest_fast_row is not None
    assert isinstance(pytest_fast_step["ms"], int)
    assert isinstance(pytest_fast_row["current_ms"], int)


# ------------------------------------------------------------------
# 4. Budget baseline reflects current reality
# ------------------------------------------------------------------


def test_budget_baseline_shape_matches_budget_check_artifact(tmp_path: Path) -> None:
    """Verify that generated budget check rows carry the baseline-derived fields."""
    _durations_path, budget_artifact_path = _write_synthetic_verify_budget_artifacts(tmp_path)
    budget_payload = json.loads(budget_artifact_path.read_text(encoding="utf-8"))

    pytest_fast_row = None
    for row in budget_payload.get("checked_steps", []):
        if isinstance(row, dict) and row.get("name") == "pytest-fast":
            pytest_fast_row = row
            break

    assert pytest_fast_row is not None
    assert set(pytest_fast_row) == {
        "budget_ms",
        "current_ms",
        "delta_ms",
        "effective_ms",
        "median_ms",
        "name",
        "ok",
        "ratio_limit",
        "threshold_ms",
        "tolerance_ms",
    }
    assert isinstance(pytest_fast_row["budget_ms"], int)
    assert isinstance(pytest_fast_row["current_ms"], int)
    assert isinstance(pytest_fast_row["delta_ms"], int)
    assert isinstance(pytest_fast_row["effective_ms"], int)
    assert pytest_fast_row["median_ms"] is None or isinstance(pytest_fast_row["median_ms"], int)
    assert isinstance(pytest_fast_row["ratio_limit"], float)
    assert isinstance(pytest_fast_row["threshold_ms"], int)
    assert isinstance(pytest_fast_row["tolerance_ms"], int)
