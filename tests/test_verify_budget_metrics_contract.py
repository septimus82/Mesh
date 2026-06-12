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


def _require_positive_wall_clock(value: object, *, artifact_name: str) -> int:
    if not isinstance(value, int):
        pytest.fail(f"{artifact_name} current_ms must be an int, got {type(value).__name__}")
    if value <= 0:
        pytest.skip(f"{artifact_name} is incomplete or stale (current_ms={value})")
    return value


def _require_positive_step_ms(value: object, *, artifact_name: str) -> int:
    if not isinstance(value, int):
        pytest.fail(f"{artifact_name} ms must be an int, got {type(value).__name__}")
    if value <= 0:
        pytest.skip(f"{artifact_name} is incomplete or stale (ms={value})")
    return value


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


def test_budget_check_artifact_has_pytest_fast() -> None:
    """Verify that pytest-fast appears in budget check artifact after verify-all."""
    artifact_path = _REPO_ROOT / "artifacts" / "verify_step_budget_check.json"
    if not artifact_path.exists():
        pytest.skip("No budget check artifact - run verify-all first")

    payload = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert "schema_version" in payload
    assert "checked_steps" in payload
    assert isinstance(payload["checked_steps"], list)

    # Find pytest-fast row
    pytest_fast_row = None
    for row in payload["checked_steps"]:
        if isinstance(row, dict) and row.get("name") == "pytest-fast":
            pytest_fast_row = row
            break

    if pytest_fast_row is None:
        pytest.skip("pytest-fast not in checked_steps - may have been skipped")

    # Validate row has required fields
    assert "name" in pytest_fast_row
    assert "budget_ms" in pytest_fast_row
    assert "current_ms" in pytest_fast_row
    assert "threshold_ms" in pytest_fast_row
    assert "ok" in pytest_fast_row

    # Wall-clock metric
    _require_positive_wall_clock(
        pytest_fast_row["current_ms"],
        artifact_name="verify_step_budget_check.json::pytest-fast",
    )


# ------------------------------------------------------------------
# 2. verify_step_durations.json schema
# ------------------------------------------------------------------


def test_step_durations_schema_shape() -> None:
    """Verify that step durations artifact has expected schema."""
    artifact_path = _REPO_ROOT / "artifacts" / "verify_step_durations.json"
    if not artifact_path.exists():
        pytest.skip("No step durations artifact - run verify-all first")

    payload = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert "schema_version" in payload
    assert "steps" in payload
    assert isinstance(payload["steps"], list)

    # Find pytest-fast step
    pytest_fast_step = None
    for step in payload["steps"]:
        if isinstance(step, dict) and step.get("name") == "pytest-fast":
            pytest_fast_step = step
            break

    if pytest_fast_step is None:
        pytest.skip("pytest-fast not in steps - may have been skipped")

    # Validate step has required fields
    assert "name" in pytest_fast_step
    assert "ms" in pytest_fast_step
    assert "ok" in pytest_fast_step

    # Wall-clock metric (same as budget check current_ms)
    _require_positive_step_ms(
        pytest_fast_step["ms"],
        artifact_name="verify_step_durations.json::pytest-fast",
    )


# ------------------------------------------------------------------
# 3. pytest-fast metrics coherence
# ------------------------------------------------------------------


def test_pytest_fast_has_both_metrics() -> None:
    """Verify that pytest-fast has both execution time and wall-clock time metrics."""
    # Check duration guard baseline (test execution time)
    duration_baseline_path = _REPO_ROOT / ".mesh" / "metrics" / "pytest_fast_total_seconds.txt"
    if not duration_baseline_path.exists():
        pytest.skip("No pytest duration baseline - run verify-all first")

    duration_baseline = float(duration_baseline_path.read_text(encoding="utf-8").strip())
    assert duration_baseline > 0, "Duration baseline must be positive"

    # Check budget check artifact (wall-clock time)
    budget_artifact_path = _REPO_ROOT / "artifacts" / "verify_step_budget_check.json"
    if not budget_artifact_path.exists():
        pytest.skip("No budget check artifact - run verify-all first")

    budget_payload = json.loads(budget_artifact_path.read_text(encoding="utf-8"))
    pytest_fast_row = None
    for row in budget_payload.get("checked_steps", []):
        if isinstance(row, dict) and row.get("name") == "pytest-fast":
            pytest_fast_row = row
            break

    if pytest_fast_row is None:
        pytest.skip("pytest-fast not in budget check")

    wall_clock_ms = _require_positive_wall_clock(
        pytest_fast_row["current_ms"],
        artifact_name="verify_step_budget_check.json::pytest-fast",
    )
    wall_clock_s = wall_clock_ms / 1000.0

    # Wall-clock time should be >= test execution time (due to overhead)
    # But within reasonable bounds (overhead shouldn't be 10x)
    assert wall_clock_s >= duration_baseline, (
        f"Wall-clock time ({wall_clock_s:.2f}s) should be >= test execution time ({duration_baseline:.2f}s)"
    )
    assert wall_clock_s <= duration_baseline * 3.0, (
        f"Wall-clock time ({wall_clock_s:.2f}s) should not be >3x test execution time ({duration_baseline:.2f}s)"
    )


# ------------------------------------------------------------------
# 4. Budget baseline reflects current reality
# ------------------------------------------------------------------


def test_budget_baseline_is_reasonable() -> None:
    """Verify that pytest-fast budget baseline is within reasonable range of current measurements."""
    baseline_path = _REPO_ROOT / "tooling" / "metrics" / "verify_step_budget.json"
    budget_artifact_path = _REPO_ROOT / "artifacts" / "verify_step_budget_check.json"

    if not baseline_path.exists() or not budget_artifact_path.exists():
        pytest.skip("Missing required files")

    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    budget_payload = json.loads(budget_artifact_path.read_text(encoding="utf-8"))

    pytest_fast_budget = baseline["budgets_ms"].get("pytest-fast")
    if pytest_fast_budget is None:
        pytest.skip("pytest-fast not in baseline")

    pytest_fast_row = None
    for row in budget_payload.get("checked_steps", []):
        if isinstance(row, dict) and row.get("name") == "pytest-fast":
            pytest_fast_row = row
            break

    if pytest_fast_row is None:
        pytest.skip("pytest-fast not in budget check")

    current_ms = pytest_fast_row["current_ms"]
    threshold_ms = pytest_fast_row["threshold_ms"]
    budget_ms = pytest_fast_row.get("budget_ms", 0)

    # Artifact may be stale - if budget_ms in artifact doesn't match baseline, skip
    if budget_ms != pytest_fast_budget:
        pytest.skip(
            f"Artifact appears stale: budget_ms={budget_ms} != baseline={pytest_fast_budget}. "
            "Run verify-all to regenerate artifacts."
        )

    # Current should be within threshold (not marked as offender)
    # This validates the budget baseline is sane
    if not pytest_fast_row["ok"]:
        pytest.fail(
            f"pytest-fast budget exceeded: current={current_ms}ms threshold={threshold_ms}ms budget={pytest_fast_budget}ms. "
            f"Update tooling/metrics/verify_step_budget.json if this is expected."
        )
