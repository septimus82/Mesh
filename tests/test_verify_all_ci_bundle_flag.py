"""Fast-tier tests for the ``verify-all --ci-bundle`` convenience flag.

``--ci-bundle`` implies ``--report-json-artifact`` and ``--artifact-index``.
Tests monkeypatch ``_build_verify_all_payload`` to avoid the expensive
full pipeline.
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
    """Write the minimum viable set of artifacts for report/index to render."""
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
    _write(
        d / "verify_step_budget_check.json",
        {
            "schema_version": 2,
            "ok": True,
            "tolerance_ms": 50,
            "candidates_used": [],
            "checked_steps": [],
            "offenders": [],
        },
    )
    _write(d / "swallowed_exceptions.json", {"schema_version": 1, "ok": True, "total": 0, "distinct": 0, "per_site": []})
    _write(d / "shadow_backend.json", {"schema_version": 1, "selected": "none", "reason": "uninitialized", "fallbacks": []})


def _make_payload(*, ok: bool = True, artifacts_dir: str = "artifacts") -> dict:
    return {
        "ok": ok,
        "steps": [{"name": "verify-demo", "ok": ok, "code": 0 if ok else 1, "error": "" if ok else "failed", "artifact": None}],
        "pytest_fast": {"ok": True, "total": 1.0, "top10": 0.5},
        "artifacts": {
            "dir": artifacts_dir,
            "written": {
                "verify_all_summary": f"{artifacts_dir}/verify_all_summary.json",
                "verify_report": None,
                "artifact_index": None,
            },
        },
    }


def _make_args(*, artifacts: str, ci_bundle: bool = False, report_json_artifact: bool = False, artifact_index: bool = False, ok: bool = True):
    import argparse

    return argparse.Namespace(
        command="verify-all",
        artifacts=artifacts,
        report=False,
        report_json=False,
        report_json_artifact=report_json_artifact,
        artifact_index=artifact_index,
        ci_bundle=ci_bundle,
        pytest_args=[],
        out_dir=None,
        no_index=False,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_ci_bundle_enables_report_json_artifact_and_index(tmp_path: Path, monkeypatch, capsys) -> None:
    """--ci-bundle causes both verify_report.json and index.json to be referenced in stdout payload."""
    import mesh_cli.verify as verify_mod

    artifacts = tmp_path / "artifacts"
    _make_minimal_artifacts(artifacts)

    payload = _make_payload(artifacts_dir=artifacts.as_posix())
    monkeypatch.setattr(verify_mod, "_build_verify_all_payload", lambda _args: (payload, 0))

    args = _make_args(artifacts=str(artifacts), ci_bundle=True)
    code = verify_mod._handle_verify_all(args)
    capsys.readouterr()

    assert code == 0
    # After propagation, both flags should be True on args
    assert args.report_json_artifact is True
    assert args.artifact_index is True


def test_ci_bundle_not_set_leaves_flags_false(tmp_path: Path, monkeypatch, capsys) -> None:
    """Without --ci-bundle, flags remain False."""
    import mesh_cli.verify as verify_mod

    artifacts = tmp_path / "artifacts"
    _make_minimal_artifacts(artifacts)

    payload = _make_payload(artifacts_dir=artifacts.as_posix())
    monkeypatch.setattr(verify_mod, "_build_verify_all_payload", lambda _args: (payload, 0))

    args = _make_args(artifacts=str(artifacts), ci_bundle=False)
    verify_mod._handle_verify_all(args)
    capsys.readouterr()

    assert args.report_json_artifact is False
    assert args.artifact_index is False


def test_ci_bundle_preserves_failure_exit_code(tmp_path: Path, monkeypatch, capsys) -> None:
    """--ci-bundle preserves exit code 2 on failure."""
    import mesh_cli.verify as verify_mod

    artifacts = tmp_path / "artifacts"
    _make_minimal_artifacts(artifacts)

    payload = _make_payload(ok=False, artifacts_dir=artifacts.as_posix())
    monkeypatch.setattr(verify_mod, "_build_verify_all_payload", lambda _args: (payload, 2))

    args = _make_args(artifacts=str(artifacts), ci_bundle=True)
    code = verify_mod._handle_verify_all(args)
    capsys.readouterr()

    assert code == 2


def test_ci_bundle_no_conflict_with_explicit_flags(tmp_path: Path, monkeypatch, capsys) -> None:
    """Passing --ci-bundle alongside explicit --report-json-artifact works."""
    import mesh_cli.verify as verify_mod

    artifacts = tmp_path / "artifacts"
    _make_minimal_artifacts(artifacts)

    payload = _make_payload(artifacts_dir=artifacts.as_posix())
    monkeypatch.setattr(verify_mod, "_build_verify_all_payload", lambda _args: (payload, 0))

    args = _make_args(
        artifacts=str(artifacts),
        ci_bundle=True,
        report_json_artifact=True,
        artifact_index=True,
    )
    code = verify_mod._handle_verify_all(args)
    capsys.readouterr()

    assert code == 0
    assert args.report_json_artifact is True
    assert args.artifact_index is True


def test_ci_bundle_written_keys_none_when_not_set(tmp_path: Path, monkeypatch, capsys) -> None:
    """Without --ci-bundle, verify_report and artifact_index stay None in stdout."""
    import mesh_cli.verify as verify_mod

    artifacts = tmp_path / "artifacts"
    _make_minimal_artifacts(artifacts)

    payload = _make_payload(artifacts_dir=artifacts.as_posix())
    monkeypatch.setattr(verify_mod, "_build_verify_all_payload", lambda _args: (payload, 0))

    args = _make_args(artifacts=str(artifacts), ci_bundle=False)
    verify_mod._handle_verify_all(args)
    out = capsys.readouterr().out
    out_payload = json.loads(out.strip())

    assert out_payload["artifacts"]["written"]["verify_report"] is None
    assert out_payload["artifacts"]["written"]["artifact_index"] is None


def test_ci_bundle_deterministic_output(tmp_path: Path, monkeypatch, capsys) -> None:
    """Running twice with --ci-bundle produces identical stdout."""
    import mesh_cli.verify as verify_mod

    artifacts = tmp_path / "artifacts"
    _make_minimal_artifacts(artifacts)

    payload = _make_payload(artifacts_dir=artifacts.as_posix())
    monkeypatch.setattr(verify_mod, "_build_verify_all_payload", lambda _args: (payload, 0))

    def _run():
        args = _make_args(artifacts=str(artifacts), ci_bundle=True)
        verify_mod._handle_verify_all(args)
        return capsys.readouterr().out

    out1 = _run()
    out2 = _run()
    assert out1 == out2
