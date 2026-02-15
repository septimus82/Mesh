"""Fast-tier tests for the authoring-trace budget guard.

Tests exercise :func:`mesh_cli.verify._evaluate_authoring_trace_budget_guard`,
:func:`mesh_cli.verify._build_authoring_trace_budget_check_payload`,
and :func:`mesh_cli.verify._authoring_trace_budget_update_command` in
isolation — no real engine/game imports, no filesystem side-effects.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_trace_payload(
    *,
    enabled: bool = True,
    total_ms: int = 10,
    functions: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Build a minimal authoring-trace artifact payload."""
    return {
        "schema_version": 1,
        "enabled": enabled,
        "total_calls": 0,
        "total_ms": total_ms,
        "functions": functions or [],
    }


def _make_baseline(
    tmp_path: Path,
    *,
    tolerance_ms: int = 5,
    total_ms_budget: int = 50,
    functions: dict[str, int] | None = None,
) -> Path:
    """Write a baseline JSON file and return its path."""
    baseline = tmp_path / "authoring_trace_budget.json"
    data = {
        "schema_version": 1,
        "tolerance_ms": tolerance_ms,
        "total_ms_budget": total_ms_budget,
        "functions": functions or {},
    }
    baseline.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return baseline


# ---------------------------------------------------------------------------
# Guard: skipped when baseline missing → pass
# ---------------------------------------------------------------------------


def test_guard_pass_when_baseline_missing(tmp_path: Path) -> None:
    from mesh_cli.verify import _evaluate_authoring_trace_budget_guard

    baseline = tmp_path / "does_not_exist.json"
    code, error, payload = _evaluate_authoring_trace_budget_guard(
        authoring_trace_payload=_make_trace_payload(),
        baseline_path=baseline,
        update_command="python -c 'noop'",
    )
    assert code == 0
    assert error == ""
    assert payload["ok"] is True
    assert payload["checked_functions"] == []
    assert payload["total_budget_ms"] is None
    assert payload["total_current_ms"] is None


# ---------------------------------------------------------------------------
# Guard: pass within budget
# ---------------------------------------------------------------------------


def test_guard_pass_within_budget(tmp_path: Path) -> None:
    from mesh_cli.verify import _evaluate_authoring_trace_budget_guard

    baseline = _make_baseline(tmp_path, total_ms_budget=100, tolerance_ms=5, functions={"foo": 20})
    trace = _make_trace_payload(
        total_ms=90,
        functions=[{"name": "foo", "total_ms": 18, "calls": 1}],
    )
    code, error, payload = _evaluate_authoring_trace_budget_guard(
        authoring_trace_payload=trace,
        baseline_path=baseline,
        update_command="python -c 'noop'",
    )
    assert code == 0
    assert error == ""
    assert payload["ok"] is True
    assert payload["total_budget_ms"] == 100
    assert payload["total_current_ms"] == 90
    assert len(payload["offenders"]) == 0


def test_guard_pass_at_exact_threshold(tmp_path: Path) -> None:
    from mesh_cli.verify import _evaluate_authoring_trace_budget_guard

    baseline = _make_baseline(tmp_path, total_ms_budget=50, tolerance_ms=5, functions={"bar": 10})
    trace = _make_trace_payload(
        total_ms=55,
        functions=[{"name": "bar", "total_ms": 15, "calls": 2}],
    )
    code, error, payload = _evaluate_authoring_trace_budget_guard(
        authoring_trace_payload=trace,
        baseline_path=baseline,
        update_command="python -c 'noop'",
    )
    assert code == 0
    assert error == ""
    assert payload["ok"] is True


# ---------------------------------------------------------------------------
# Guard: fail on total_ms excess
# ---------------------------------------------------------------------------


def test_guard_fail_total_ms_exceeded(tmp_path: Path) -> None:
    from mesh_cli.verify import _evaluate_authoring_trace_budget_guard

    baseline = _make_baseline(tmp_path, total_ms_budget=50, tolerance_ms=5)
    trace = _make_trace_payload(total_ms=60)  # 60 > 50 + 5
    code, error, payload = _evaluate_authoring_trace_budget_guard(
        authoring_trace_payload=trace,
        baseline_path=baseline,
        update_command="python -c 'update'",
    )
    assert code == 2
    assert "authoring-trace budget exceeded" in error
    assert "total:" in error
    assert "update baseline with:" in error
    assert payload["ok"] is False


# ---------------------------------------------------------------------------
# Guard: fail on per-function excess
# ---------------------------------------------------------------------------


def test_guard_fail_function_exceeded(tmp_path: Path) -> None:
    from mesh_cli.verify import _evaluate_authoring_trace_budget_guard

    baseline = _make_baseline(
        tmp_path,
        total_ms_budget=200,
        tolerance_ms=5,
        functions={"alpha": 10, "beta": 20},
    )
    trace = _make_trace_payload(
        total_ms=50,
        functions=[
            {"name": "alpha", "total_ms": 20, "calls": 3},  # 20 > 10 + 5 → fail
            {"name": "beta", "total_ms": 22, "calls": 1},   # 22 <= 20 + 5 → pass
        ],
    )
    code, error, payload = _evaluate_authoring_trace_budget_guard(
        authoring_trace_payload=trace,
        baseline_path=baseline,
        update_command="python -c 'update'",
    )
    assert code == 2
    assert "alpha:" in error
    assert "beta:" not in error
    assert payload["ok"] is False
    assert len(payload["offenders"]) == 1
    assert payload["offenders"][0]["name"] == "alpha"


# ---------------------------------------------------------------------------
# Guard: violation ordering is deterministic (delta desc, name asc)
# ---------------------------------------------------------------------------


def test_guard_offenders_ordering_deterministic(tmp_path: Path) -> None:
    from mesh_cli.verify import _evaluate_authoring_trace_budget_guard

    baseline = _make_baseline(
        tmp_path,
        total_ms_budget=999,
        tolerance_ms=0,
        functions={"charlie": 5, "alpha": 5, "bravo": 5},
    )
    trace = _make_trace_payload(
        total_ms=10,
        functions=[
            {"name": "charlie", "total_ms": 15, "calls": 1},  # delta 10
            {"name": "alpha", "total_ms": 15, "calls": 1},    # delta 10
            {"name": "bravo", "total_ms": 25, "calls": 1},    # delta 20
        ],
    )
    code, error, payload = _evaluate_authoring_trace_budget_guard(
        authoring_trace_payload=trace,
        baseline_path=baseline,
        update_command="irrelevant",
    )
    assert code == 2
    names = [o["name"] for o in payload["offenders"]]
    assert names == ["bravo", "alpha", "charlie"]


# ---------------------------------------------------------------------------
# Guard: error message contains update command
# ---------------------------------------------------------------------------


def test_guard_fail_message_contains_update_command(tmp_path: Path) -> None:
    from mesh_cli.verify import _evaluate_authoring_trace_budget_guard

    baseline = _make_baseline(tmp_path, total_ms_budget=0, tolerance_ms=0)
    trace = _make_trace_payload(total_ms=99)
    cmd = "python -c 'the-update-command'"
    code, error, _payload = _evaluate_authoring_trace_budget_guard(
        authoring_trace_payload=trace,
        baseline_path=baseline,
        update_command=cmd,
    )
    assert code == 2
    assert cmd in error


# ---------------------------------------------------------------------------
# Guard: malformed baseline returns code 1
# ---------------------------------------------------------------------------


def test_guard_code1_on_malformed_baseline(tmp_path: Path) -> None:
    from mesh_cli.verify import _evaluate_authoring_trace_budget_guard

    baseline = tmp_path / "bad.json"
    baseline.write_text("not json at all", encoding="utf-8")
    code, error, payload = _evaluate_authoring_trace_budget_guard(
        authoring_trace_payload=_make_trace_payload(),
        baseline_path=baseline,
        update_command="noop",
    )
    assert code == 1
    assert "parse failed" in error
    assert payload["ok"] is False


def test_guard_code1_on_non_object_baseline(tmp_path: Path) -> None:
    from mesh_cli.verify import _evaluate_authoring_trace_budget_guard

    baseline = tmp_path / "list.json"
    baseline.write_text("[1,2,3]", encoding="utf-8")
    code, error, payload = _evaluate_authoring_trace_budget_guard(
        authoring_trace_payload=_make_trace_payload(),
        baseline_path=baseline,
        update_command="noop",
    )
    assert code == 1
    assert "must be an object" in error
    assert payload["ok"] is False


# ---------------------------------------------------------------------------
# Check payload builder: schema shape
# ---------------------------------------------------------------------------


def test_check_payload_schema_shape() -> None:
    from mesh_cli.verify import _build_authoring_trace_budget_check_payload

    payload = _build_authoring_trace_budget_check_payload(
        ok=True,
        tolerance_ms=5,
        total_budget_ms=50,
        total_current_ms=10,
        checked_functions=[
            {
                "name": "z_func",
                "budget_ms": 20,
                "tolerance_ms": 5,
                "current_ms": 10,
                "delta_ms": -15,
                "ok": True,
            },
            {
                "name": "a_func",
                "budget_ms": 10,
                "tolerance_ms": 5,
                "current_ms": 5,
                "delta_ms": -10,
                "ok": True,
            },
        ],
    )
    assert payload["schema_version"] == 1
    assert payload["ok"] is True
    assert payload["tolerance_ms"] == 5
    assert payload["total_budget_ms"] == 50
    assert payload["total_current_ms"] == 10
    assert payload["offenders"] == []
    # checked_functions sorted by name
    names = [f["name"] for f in payload["checked_functions"]]
    assert names == ["a_func", "z_func"]


# ---------------------------------------------------------------------------
# Update command: deterministic and Windows-safe
# ---------------------------------------------------------------------------


def test_update_command_is_deterministic() -> None:
    from mesh_cli.verify import _authoring_trace_budget_update_command

    cmd1 = _authoring_trace_budget_update_command(Path("artifacts"))
    cmd2 = _authoring_trace_budget_update_command(Path("artifacts"))
    assert cmd1 == cmd2
    assert "python -c" in cmd1
    assert "authoring_trace.json" in cmd1
    assert "authoring_trace_budget.json" in cmd1


def test_update_command_none_artifacts_dir() -> None:
    from mesh_cli.verify import _authoring_trace_budget_update_command

    cmd = _authoring_trace_budget_update_command(None)
    assert "python -c" in cmd
    assert "artifacts" in cmd  # falls back to default


# ---------------------------------------------------------------------------
# Guard: function not in baseline is not checked
# ---------------------------------------------------------------------------


def test_guard_ignores_functions_not_in_baseline(tmp_path: Path) -> None:
    from mesh_cli.verify import _evaluate_authoring_trace_budget_guard

    baseline = _make_baseline(
        tmp_path,
        total_ms_budget=999,
        tolerance_ms=5,
        functions={"tracked": 30},
    )
    trace = _make_trace_payload(
        total_ms=10,
        functions=[
            {"name": "tracked", "total_ms": 20, "calls": 1},   # within budget
            {"name": "untracked", "total_ms": 999, "calls": 1}, # not in baseline → ignored
        ],
    )
    code, error, payload = _evaluate_authoring_trace_budget_guard(
        authoring_trace_payload=trace,
        baseline_path=baseline,
        update_command="noop",
    )
    assert code == 0
    assert payload["ok"] is True
    checked_names = [f["name"] for f in payload["checked_functions"]]
    assert "tracked" in checked_names
    assert "untracked" not in checked_names
