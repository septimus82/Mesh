"""Fast-tier tests for the ``verify-all --report`` and ``--report-json`` flags.

Tests monkeypatch ``_build_verify_all_payload`` to avoid the expensive
full pipeline, write minimal artifact files, and assert that the
report text / JSON appears (or doesn't) in stdout depending on the flag.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _make_minimal_artifacts(d: Path) -> None:
    """Write the minimum viable set of artifacts for the report to render."""
    _write(
        d / "verify_all_summary.json",
        {
            "ok": True,
            "steps": [{"name": "verify-demo", "ok": True, "code": 0, "error": "", "artifact": None}],
            "pytest_fast": {"ok": True, "total": 1.0, "top10": 0.5},
            "artifacts": {"dir": d.as_posix(), "written": {"verify_all_summary": d.as_posix() + "/verify_all_summary.json"}},
        },
    )
    _write(d / "exception_budget.json", {"schema_version": 1, "ok": True, "current_count": 5, "baseline_count": 5, "files_scanned": [], "per_file_counts": {}})
    _write(d / "verify_step_durations.json", {"schema_version": 1, "total_ms": 100, "steps": [{"name": "verify-demo", "ms": 100, "ok": True}]})
    _write(d / "verify_step_budget_check.json", {"schema_version": 2, "ok": True, "tolerance_ms": 50, "candidates_used": [], "checked_steps": [], "offenders": []})
    _write(d / "swallowed_exceptions.json", {"schema_version": 1, "ok": True, "total": 0, "distinct": 0, "per_site": []})
    _write(d / "shadow_backend.json", {"schema_version": 1, "selected": "none", "reason": "uninitialized", "fallbacks": []})


def _make_payload(*, ok: bool = True, artifacts_dir: str = "artifacts") -> dict:
    return {
        "ok": ok,
        "steps": [{"name": "verify-demo", "ok": ok, "code": 0 if ok else 1, "error": "" if ok else "failed", "artifact": None}],
        "pytest_fast": {"ok": True, "total": 1.0, "top10": 0.5},
        "artifacts": {"dir": artifacts_dir, "written": {"verify_all_summary": f"{artifacts_dir}/verify_all_summary.json"}},
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_report_flag_prints_doctor_report(tmp_path: Path, monkeypatch, capsys) -> None:
    """With --report, stdout contains Doctor Report after the JSON."""
    import argparse

    import mesh_cli.verify as verify_mod

    artifacts = tmp_path / "artifacts"
    _make_minimal_artifacts(artifacts)

    payload = _make_payload(artifacts_dir=artifacts.as_posix())
    monkeypatch.setattr(verify_mod, "_build_verify_all_payload", lambda _args: (payload, 0))

    args = argparse.Namespace(
        command="verify-all",
        artifacts=str(artifacts),
        report=True,
        pytest_args=[],
        out_dir=None,
        no_index=False,
    )
    code = verify_mod._handle_verify_all(args)
    out = capsys.readouterr().out

    assert code == 0
    # JSON payload present
    assert '"ok": true' in out
    # Report sections present after JSON
    assert "Doctor Report" in out
    assert "=== Verify Summary ===" in out
    assert "=== Budgets ===" in out
    assert "=== Timing ===" in out
    assert "=== Artifacts Read ===" in out


def test_no_report_flag_omits_doctor_report(tmp_path: Path, monkeypatch, capsys) -> None:
    """Without --report, stdout is pure JSON — no Doctor Report."""
    import argparse

    import mesh_cli.verify as verify_mod

    artifacts = tmp_path / "artifacts"
    _make_minimal_artifacts(artifacts)

    payload = _make_payload(artifacts_dir=artifacts.as_posix())
    monkeypatch.setattr(verify_mod, "_build_verify_all_payload", lambda _args: (payload, 0))

    args = argparse.Namespace(
        command="verify-all",
        artifacts=str(artifacts),
        report=False,
        pytest_args=[],
        out_dir=None,
        no_index=False,
    )
    code = verify_mod._handle_verify_all(args)
    out = capsys.readouterr().out

    assert code == 0
    assert '"ok": true' in out
    assert "Doctor Report" not in out


def test_report_flag_preserves_failure_exit_code(tmp_path: Path, monkeypatch, capsys) -> None:
    """On failure (exit 2), --report still prints report and preserves exit code."""
    import argparse

    import mesh_cli.verify as verify_mod

    artifacts = tmp_path / "artifacts"
    _make_minimal_artifacts(artifacts)

    payload = _make_payload(ok=False, artifacts_dir=artifacts.as_posix())
    monkeypatch.setattr(verify_mod, "_build_verify_all_payload", lambda _args: (payload, 2))

    args = argparse.Namespace(
        command="verify-all",
        artifacts=str(artifacts),
        report=True,
        pytest_args=[],
        out_dir=None,
        no_index=False,
    )
    code = verify_mod._handle_verify_all(args)
    out = capsys.readouterr().out

    assert code == 2
    assert "Doctor Report" in out
    assert '"ok": false' in out


def test_report_flag_no_artifacts_dir_no_crash(tmp_path: Path, monkeypatch, capsys) -> None:
    """--report with no --artifacts doesn't crash."""
    import argparse

    import mesh_cli.verify as verify_mod

    payload = _make_payload()
    monkeypatch.setattr(verify_mod, "_build_verify_all_payload", lambda _args: (payload, 0))

    args = argparse.Namespace(
        command="verify-all",
        artifacts="",
        report=True,
        pytest_args=[],
        out_dir=None,
        no_index=False,
    )
    code = verify_mod._handle_verify_all(args)
    out = capsys.readouterr().out

    assert code == 0
    # No crash, no report (since artifacts dir is empty string)
    assert "Doctor Report" not in out


def test_report_flag_missing_dir_no_crash(tmp_path: Path, monkeypatch, capsys) -> None:
    """--report with nonexistent artifacts dir doesn't crash."""
    import argparse

    import mesh_cli.verify as verify_mod

    nonexistent = tmp_path / "does_not_exist"
    payload = _make_payload(artifacts_dir=str(nonexistent))
    monkeypatch.setattr(verify_mod, "_build_verify_all_payload", lambda _args: (payload, 0))

    args = argparse.Namespace(
        command="verify-all",
        artifacts=str(nonexistent),
        report=True,
        pytest_args=[],
        out_dir=None,
        no_index=False,
    )
    code = verify_mod._handle_verify_all(args)
    out = capsys.readouterr().out

    assert code == 0
    assert "Doctor Report" not in out


def test_report_output_deterministic(tmp_path: Path, monkeypatch, capsys) -> None:
    """Running twice with --report produces identical output."""
    import argparse

    import mesh_cli.verify as verify_mod

    artifacts = tmp_path / "artifacts"
    _make_minimal_artifacts(artifacts)

    payload = _make_payload(artifacts_dir=artifacts.as_posix())
    monkeypatch.setattr(verify_mod, "_build_verify_all_payload", lambda _args: (payload, 0))

    def _run():
        args = argparse.Namespace(
            command="verify-all",
            artifacts=str(artifacts),
            report=True,
            pytest_args=[],
            out_dir=None,
            no_index=False,
        )
        verify_mod._handle_verify_all(args)
        return capsys.readouterr().out

    out1 = _run()
    out2 = _run()
    assert out1 == out2


# ---------------------------------------------------------------------------
# --report-json tests
# ---------------------------------------------------------------------------


def test_report_json_flag_prints_json_payload(tmp_path: Path, monkeypatch, capsys) -> None:
    """With --report-json, stdout contains a valid JSON payload after the main JSON."""
    import argparse

    import mesh_cli.verify as verify_mod

    artifacts = tmp_path / "artifacts"
    _make_minimal_artifacts(artifacts)

    payload = _make_payload(artifacts_dir=artifacts.as_posix())
    monkeypatch.setattr(verify_mod, "_build_verify_all_payload", lambda _args: (payload, 0))

    args = argparse.Namespace(
        command="verify-all",
        artifacts=str(artifacts),
        report=False,
        report_json=True,
        pytest_args=[],
        out_dir=None,
        no_index=False,
    )
    code = verify_mod._handle_verify_all(args)
    out = capsys.readouterr().out

    assert code == 0

    # Find the second JSON object (the report payload)
    # The main payload ends, then the report JSON follows after a newline
    parts = out.split("\n\n")
    assert len(parts) >= 2, f"Expected at least two blocks separated by blank line, got {len(parts)}"

    report_json_text = parts[-1].strip()
    report = json.loads(report_json_text)

    assert report["schema_version"] == 1
    assert "verify_summary" in report
    assert "budgets" in report
    assert "timing" in report
    assert "runtime_diagnostics" in report
    assert "read_files" in report
    assert "artifacts_dir" in report


def test_report_json_has_schema_version_1(tmp_path: Path, monkeypatch, capsys) -> None:
    """The JSON report payload has schema_version=1."""
    import argparse

    import mesh_cli.verify as verify_mod

    artifacts = tmp_path / "artifacts"
    _make_minimal_artifacts(artifacts)

    payload = _make_payload(artifacts_dir=artifacts.as_posix())
    monkeypatch.setattr(verify_mod, "_build_verify_all_payload", lambda _args: (payload, 0))

    args = argparse.Namespace(
        command="verify-all",
        artifacts=str(artifacts),
        report=False,
        report_json=True,
        pytest_args=[],
        out_dir=None,
        no_index=False,
    )
    verify_mod._handle_verify_all(args)
    out = capsys.readouterr().out

    parts = out.split("\n\n")
    report = json.loads(parts[-1].strip())
    assert report["schema_version"] == 1


def test_no_report_json_flag_omits_report(tmp_path: Path, monkeypatch, capsys) -> None:
    """Without --report-json, stdout is pure verify-all JSON."""
    import argparse

    import mesh_cli.verify as verify_mod

    artifacts = tmp_path / "artifacts"
    _make_minimal_artifacts(artifacts)

    payload = _make_payload(artifacts_dir=artifacts.as_posix())
    monkeypatch.setattr(verify_mod, "_build_verify_all_payload", lambda _args: (payload, 0))

    args = argparse.Namespace(
        command="verify-all",
        artifacts=str(artifacts),
        report=False,
        report_json=False,
        pytest_args=[],
        out_dir=None,
        no_index=False,
    )
    verify_mod._handle_verify_all(args)
    out = capsys.readouterr().out

    assert "schema_version" not in out
    assert "Doctor Report" not in out


def test_report_json_preserves_failure_exit_code(tmp_path: Path, monkeypatch, capsys) -> None:
    """On failure (exit 2), --report-json still prints and preserves exit code."""
    import argparse

    import mesh_cli.verify as verify_mod

    artifacts = tmp_path / "artifacts"
    _make_minimal_artifacts(artifacts)

    payload = _make_payload(ok=False, artifacts_dir=artifacts.as_posix())
    monkeypatch.setattr(verify_mod, "_build_verify_all_payload", lambda _args: (payload, 2))

    args = argparse.Namespace(
        command="verify-all",
        artifacts=str(artifacts),
        report=False,
        report_json=True,
        pytest_args=[],
        out_dir=None,
        no_index=False,
    )
    code = verify_mod._handle_verify_all(args)
    out = capsys.readouterr().out

    assert code == 2
    parts = out.split("\n\n")
    report = json.loads(parts[-1].strip())
    assert report["schema_version"] == 1


def test_report_json_missing_dir_no_crash(tmp_path: Path, monkeypatch, capsys) -> None:
    """--report-json with nonexistent artifacts dir doesn't crash."""
    import argparse

    import mesh_cli.verify as verify_mod

    nonexistent = tmp_path / "does_not_exist"
    payload = _make_payload(artifacts_dir=str(nonexistent))
    monkeypatch.setattr(verify_mod, "_build_verify_all_payload", lambda _args: (payload, 0))

    args = argparse.Namespace(
        command="verify-all",
        artifacts=str(nonexistent),
        report=False,
        report_json=True,
        pytest_args=[],
        out_dir=None,
        no_index=False,
    )
    code = verify_mod._handle_verify_all(args)
    out = capsys.readouterr().out

    assert code == 0
    # No report JSON appended since dir doesn't exist
    assert "schema_version" not in out


def test_report_json_no_artifacts_arg_no_crash(tmp_path: Path, monkeypatch, capsys) -> None:
    """--report-json with empty --artifacts arg doesn't crash."""
    import argparse

    import mesh_cli.verify as verify_mod

    payload = _make_payload()
    monkeypatch.setattr(verify_mod, "_build_verify_all_payload", lambda _args: (payload, 0))

    args = argparse.Namespace(
        command="verify-all",
        artifacts="",
        report=False,
        report_json=True,
        pytest_args=[],
        out_dir=None,
        no_index=False,
    )
    code = verify_mod._handle_verify_all(args)
    out = capsys.readouterr().out

    assert code == 0
    assert "schema_version" not in out


def test_report_json_deterministic(tmp_path: Path, monkeypatch, capsys) -> None:
    """Running twice with --report-json produces identical output."""
    import argparse

    import mesh_cli.verify as verify_mod

    artifacts = tmp_path / "artifacts"
    _make_minimal_artifacts(artifacts)

    payload = _make_payload(artifacts_dir=artifacts.as_posix())
    monkeypatch.setattr(verify_mod, "_build_verify_all_payload", lambda _args: (payload, 0))

    def _run():
        args = argparse.Namespace(
            command="verify-all",
            artifacts=str(artifacts),
            report=False,
            report_json=True,
            pytest_args=[],
            out_dir=None,
            no_index=False,
        )
        verify_mod._handle_verify_all(args)
        return capsys.readouterr().out

    out1 = _run()
    out2 = _run()
    assert out1 == out2


def test_both_report_and_report_json(tmp_path: Path, monkeypatch, capsys) -> None:
    """Both --report and --report-json together: text first, then JSON."""
    import argparse

    import mesh_cli.verify as verify_mod

    artifacts = tmp_path / "artifacts"
    _make_minimal_artifacts(artifacts)

    payload = _make_payload(artifacts_dir=artifacts.as_posix())
    monkeypatch.setattr(verify_mod, "_build_verify_all_payload", lambda _args: (payload, 0))

    args = argparse.Namespace(
        command="verify-all",
        artifacts=str(artifacts),
        report=True,
        report_json=True,
        pytest_args=[],
        out_dir=None,
        no_index=False,
    )
    code = verify_mod._handle_verify_all(args)
    out = capsys.readouterr().out

    assert code == 0
    # Text report appears before JSON report
    doctor_pos = out.index("Doctor Report")
    schema_pos = out.index('"schema_version"')
    assert doctor_pos < schema_pos


def test_report_json_verify_summary_reflects_artifacts(tmp_path: Path, monkeypatch, capsys) -> None:
    """The JSON report payload verify_summary reflects the artifacts content."""
    import argparse

    import mesh_cli.verify as verify_mod

    artifacts = tmp_path / "artifacts"
    _make_minimal_artifacts(artifacts)

    payload = _make_payload(artifacts_dir=artifacts.as_posix())
    monkeypatch.setattr(verify_mod, "_build_verify_all_payload", lambda _args: (payload, 0))

    args = argparse.Namespace(
        command="verify-all",
        artifacts=str(artifacts),
        report=False,
        report_json=True,
        pytest_args=[],
        out_dir=None,
        no_index=False,
    )
    verify_mod._handle_verify_all(args)
    out = capsys.readouterr().out

    parts = out.split("\n\n")
    report = json.loads(parts[-1].strip())

    vs = report["verify_summary"]
    assert vs["ok"] is True
    assert vs["failing_steps"] == []
    assert len(vs["artifacts_written"]) >= 1

    # Budgets populated from artifacts
    assert report["budgets"]["exception_budget"] is not None
    assert report["budgets"]["exception_budget"]["ok"] is True

    # Timing populated
    assert report["timing"]["total_ms"] == 100
    assert len(report["timing"]["top5"]) == 1

    # Read files list
    assert len(report["read_files"]) == 6  # 6 required artifacts written
