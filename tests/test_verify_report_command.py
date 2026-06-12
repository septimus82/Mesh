"""Fast-tier tests for the ``verify-report`` CLI command.

All tests are self-contained — they build temporary artifact directories
with minimal valid JSON files and assert deterministic stdout output.
No engine or arcade imports.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]


# ---------------------------------------------------------------------------
# Helpers — minimal artifact factories
# ---------------------------------------------------------------------------


def _write(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _make_verify_all_summary(*, ok: bool = True, failing: list[str] | None = None) -> dict:
    steps = []
    names = ["verify-demo", "pytest-fast", "mypy-gate"]
    for name in names:
        step_ok = name not in (failing or [])
        steps.append({"name": name, "ok": step_ok, "code": 0 if step_ok else 1, "error": "" if step_ok else "failed", "artifact": None})
    return {
        "ok": ok,
        "steps": steps,
        "pytest_fast": {"ok": True, "total": 1.0, "top10": 0.5},
        "artifacts": {
            "dir": "artifacts",
            "written": {
                "verify_all_summary": "artifacts/verify_all_summary.json",
                "verify_step_durations": "artifacts/verify_step_durations.json",
                "verify_step_budget_check": "artifacts/verify_step_budget_check.json",
                "shadow_backend": "artifacts/shadow_backend.json",
                "swallowed_exceptions": "artifacts/swallowed_exceptions.json",
                "exception_budget": "artifacts/exception_budget.json",
                "authoring_trace": None,
                "authoring_trace_budget_check": None,
            },
        },
    }


def _make_exception_budget(*, ok: bool = True, current: int = 10, baseline: int = 10) -> dict:
    return {"schema_version": 1, "ok": ok, "current_count": current, "baseline_count": baseline, "files_scanned": [], "per_file_counts": {}}


def _make_step_durations(*, total_ms: int = 5000, steps: list[dict] | None = None) -> dict:
    if steps is None:
        steps = [
            {"name": "verify-demo", "ms": 3000, "ok": True},
            {"name": "pytest-fast", "ms": 1500, "ok": True},
            {"name": "mypy-gate", "ms": 500, "ok": True},
        ]
    return {"schema_version": 1, "total_ms": total_ms, "steps": steps}


def _make_step_budget_check(*, ok: bool = True, offenders: list[dict] | None = None) -> dict:
    return {
        "schema_version": 2,
        "ok": ok,
        "tolerance_ms": 50,
        "candidates_used": [],
        "checked_steps": [],
        "offenders": offenders or [],
    }


def _make_swallowed(*, total: int = 0, distinct: int = 0) -> dict:
    return {"schema_version": 1, "ok": True, "total": total, "distinct": distinct, "per_site": []}


def _make_shadow_backend(*, selected: str = "none", reason: str = "uninitialized") -> dict:
    return {"schema_version": 1, "selected": selected, "reason": reason, "fallbacks": []}


def _make_authoring_trace(
    *, enabled: bool = True, total_calls: int = 5, functions: list[dict] | None = None,
) -> dict:
    return {
        "schema_version": 1,
        "enabled": enabled,
        "total_calls": total_calls,
        "total_ms": 42,
        "functions": functions or [
            {"name": "snap_to_grid", "calls": 3, "total_ms": 30, "avg_ms": 10.0, "last_err": None},
            {"name": "paint_tile", "calls": 2, "total_ms": 12, "avg_ms": 6.0, "last_err": "TypeError"},
        ],
    }


def _make_trace_budget_check(*, ok: bool = True) -> dict:
    return {
        "schema_version": 1,
        "ok": ok,
        "tolerance_ms": 5,
        "total_budget_ms": 50,
        "total_current_ms": 10,
        "checked_functions": [],
        "offenders": [],
    }


def _populate_full(d: Path, *, with_trace: bool = False) -> None:
    """Write all standard artifacts into *d*."""
    _write(d / "verify_all_summary.json", _make_verify_all_summary())
    _write(d / "exception_budget.json", _make_exception_budget())
    _write(d / "verify_step_durations.json", _make_step_durations())
    _write(d / "verify_step_budget_check.json", _make_step_budget_check())
    _write(d / "swallowed_exceptions.json", _make_swallowed())
    _write(d / "shadow_backend.json", _make_shadow_backend())
    if with_trace:
        _write(d / "authoring_trace.json", _make_authoring_trace())
        _write(d / "authoring_trace_budget_check.json", _make_trace_budget_check())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_full_artifacts_report(tmp_path: Path) -> None:
    """All artifacts present — every section populated, no placeholders."""
    from mesh_cli.verify_report import build_report_lines

    d = tmp_path / "artifacts"
    _populate_full(d)
    lines = build_report_lines(d)
    text = "\n".join(lines)

    assert "Doctor Report" in text
    assert "=== Verify Summary ===" in text
    assert "ok: true" in text
    assert "failing_steps: (none)" in text
    assert "=== Budgets ===" in text
    assert "exception_budget: 10/10 ok=true" in text
    assert "verify_step_budget: ok=true" in text
    assert "=== Timing ===" in text
    assert "verify_total_ms: 5000" in text
    assert "verify-demo: 3000 ms" in text
    assert "=== Runtime Diagnostics ===" in text
    assert "swallowed_exceptions:" in text
    assert "shadow_backend:" in text
    assert "=== Artifacts Read ===" in text
    # No authoring trace section when not present
    assert "=== Authoring Trace ===" not in text


def test_full_artifacts_with_trace(tmp_path: Path) -> None:
    """When authoring trace artifacts are present, section appears."""
    from mesh_cli.verify_report import build_report_lines

    d = tmp_path / "artifacts"
    _populate_full(d, with_trace=True)
    lines = build_report_lines(d)
    text = "\n".join(lines)

    assert "=== Authoring Trace ===" in text
    assert "enabled: true" in text
    assert "total_calls: 5" in text
    assert "snap_to_grid:" in text
    assert "last_err=TypeError" in text
    assert "authoring_trace_budget: ok=true" in text
    assert "authoring_trace.json" in text
    assert "authoring_trace_budget_check.json" in text


def test_missing_artifacts_placeholders(tmp_path: Path) -> None:
    """Only verify_all_summary present — rest get ``?`` placeholders."""
    from mesh_cli.verify_report import build_report_lines

    d = tmp_path / "artifacts"
    _write(d / "verify_all_summary.json", _make_verify_all_summary())
    lines = build_report_lines(d)
    text = "\n".join(lines)

    assert "ok: true" in text
    assert "exception_budget: ?" in text
    assert "verify_step_budget: ?" in text
    assert "verify_total_ms: ?" in text
    assert "swallowed_exceptions: ?" in text
    assert "shadow_backend: ?" in text


def test_corrupt_json_graceful(tmp_path: Path) -> None:
    """One file corrupt — its section gets placeholders, rest OK."""
    from mesh_cli.verify_report import build_report_lines

    d = tmp_path / "artifacts"
    _populate_full(d)
    # Corrupt the exception_budget file
    (d / "exception_budget.json").write_text("NOT VALID JSON {{{{", encoding="utf-8")
    lines = build_report_lines(d)
    text = "\n".join(lines)

    assert "exception_budget: ?" in text
    # Other sections still work
    assert "verify_step_budget: ok=true" in text
    assert "verify_total_ms: 5000" in text


def test_deterministic_output(tmp_path: Path) -> None:
    """Running twice produces identical output."""
    from mesh_cli.verify_report import build_report_lines

    d = tmp_path / "artifacts"
    _populate_full(d, with_trace=True)
    run1 = "\n".join(build_report_lines(d))
    run2 = "\n".join(build_report_lines(d))
    assert run1 == run2


def test_missing_artifacts_dir_exit_code(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Missing artifacts dir → exit code 2 and message."""
    import argparse

    from mesh_cli.verify_report import _handle_verify_report

    args = argparse.Namespace(artifacts=str(tmp_path / "nonexistent"))
    code = _handle_verify_report(args)
    assert code == 2
    captured = capsys.readouterr()
    assert "not found" in captured.err


def test_failing_steps_listed(tmp_path: Path) -> None:
    """Failing steps appear in the summary."""
    from mesh_cli.verify_report import build_report_lines

    d = tmp_path / "artifacts"
    _write(d / "verify_all_summary.json", _make_verify_all_summary(ok=False, failing=["mypy-gate"]))
    lines = build_report_lines(d)
    text = "\n".join(lines)
    assert "ok: false" in text
    assert "failing_steps: mypy-gate" in text


def test_step_budget_offender_shown(tmp_path: Path) -> None:
    """Step budget worst offender appears in the budgets section."""
    from mesh_cli.verify_report import build_report_lines

    d = tmp_path / "artifacts"
    _populate_full(d)
    _write(
        d / "verify_step_budget_check.json",
        _make_step_budget_check(
            ok=False,
            offenders=[{"name": "mypy-gate", "delta_ms": 500, "effective_ms": 9500}],
        ),
    )
    lines = build_report_lines(d)
    text = "\n".join(lines)
    assert "verify_step_budget: ok=false worst=mypy-gate delta_ms=500" in text


def test_swallowed_exceptions_top_sites(tmp_path: Path) -> None:
    """Per-site breakdown appears when swallowed exceptions exist."""
    from mesh_cli.verify_report import build_report_lines

    d = tmp_path / "artifacts"
    _populate_full(d)
    payload = {
        "schema_version": 1,
        "ok": True,
        "total": 7,
        "distinct": 2,
        "per_site": [
            {"site": "engine/tick.py:42", "count": 5},
            {"site": "engine/render.py:10", "count": 2},
        ],
    }
    _write(d / "swallowed_exceptions.json", payload)
    lines = build_report_lines(d)
    text = "\n".join(lines)
    assert "total=7 distinct=2" in text
    assert "engine/tick.py:42: count=5" in text
    assert "engine/render.py:10: count=2" in text


def test_footer_lists_only_read_artifacts(tmp_path: Path) -> None:
    """Footer only lists artifacts that were actually read."""
    from mesh_cli.verify_report import build_report_lines

    d = tmp_path / "artifacts"
    _write(d / "verify_all_summary.json", _make_verify_all_summary())
    _write(d / "shadow_backend.json", _make_shadow_backend())
    lines = build_report_lines(d)
    text = "\n".join(lines)
    assert "verify_all_summary.json" in text
    assert "shadow_backend.json" in text
    assert "exception_budget.json" not in text  # not written, so not in footer


def test_empty_artifacts_dir(tmp_path: Path) -> None:
    """Empty dir — all placeholders, exit code 0."""
    from mesh_cli.verify_report import build_report_lines

    d = tmp_path / "artifacts"
    d.mkdir()
    lines = build_report_lines(d)
    text = "\n".join(lines)

    assert "ok: ?" in text
    assert "exception_budget: ?" in text
    assert "(none)" in text  # footer shows no artifacts read
