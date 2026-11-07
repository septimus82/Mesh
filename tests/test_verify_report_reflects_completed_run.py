"""verify-all's derived reports (verify_report.json, release notes, index.json) describe the run that wrote them:
verify_all_summary.json is written once the outcome is settled and before them, and rewritten at the end to list them.
Before this (#360) the report was built before the summary existed and said ``verify_summary.ok: null``."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from tests.test_verify_release_notes_artifacts import _patch_fast_success, _seed_repo

pytestmark = [pytest.mark.fast]

_BASELINE = Path(__file__).resolve().parents[1] / "tooling" / "metrics" / "ci_baseline_artifacts"


def _ci_bundle_args() -> argparse.Namespace:
    return argparse.Namespace(
        command="verify-all", world=None, out_dir=None, artifacts="artifacts", no_index=False, report=False,
        report_json=False, report_json_artifact=True, artifact_index=True, ci_bundle=False,
        release_notes_artifact=True, pytest_args=[],
    )


def _run(monkeypatch: pytest.MonkeyPatch, repo: Path) -> tuple[dict, int, Path]:
    import mesh_cli.verify as verify_mod

    _seed_repo(repo)
    monkeypatch.chdir(repo)
    payload, code = verify_mod._build_verify_all_payload(_ci_bundle_args())
    return payload, code, repo / "artifacts"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _gate(curr: Path) -> int:
    from mesh_cli.artifacts_diff import _handle_artifacts_diff

    return _handle_artifacts_diff(argparse.Namespace(
        base=str(_BASELINE), curr=str(curr), format="text", fail_on_regression=True, out=""))


def test_a_successful_run_reports_ok_true_from_the_summary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_fast_success(monkeypatch)
    payload, code, artifacts = _run(monkeypatch, tmp_path / "repo")

    assert code == 0 and payload["ok"] is True
    report = _read(artifacts / "verify_report.json")
    assert report["verify_summary"]["ok"] is True
    assert report["verify_summary"]["failing_steps"] == []
    assert "verify_all_summary.json" in report["read_files"], "the summary existed when the report was built"
    assert _read(artifacts / "release_notes.json")["snapshot"]["verify_ok"] is True
    # The final summary lists the reports derived from it; the index points at both.
    written = _read(artifacts / "verify_all_summary.json")["artifacts"]["written"]
    assert written["verify_report"] == "artifacts/verify_report.json"
    assert written["artifact_index"] == "artifacts/index.json"
    index = _read(artifacts / "index.json")
    assert index["ok"] is True
    assert index["written"]["verify_report"] == "artifacts/verify_report.json"
    assert index["written"]["verify_all_summary"] == "artifacts/verify_all_summary.json"
    assert _gate(artifacts) == 0, "a healthy run passes the CI baseline diff"


def test_a_failed_step_is_reported_as_a_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import mesh_cli.verify as verify_mod

    _patch_fast_success(monkeypatch)

    def _one_step_fails(ctx) -> None:
        for name in verify_mod.VERIFY_ALL_STEPS:
            failed = name == "ruff-gate"
            ctx.add_step(name, 1 if failed else 0, error="failed" if failed else "", artifact=None)
            ctx.step_duration_rows.append({"name": name, "ok": not failed, "ms": 1})
        ctx.pytest_fast_metrics = {"ok": True, "total": 1.0, "top10": 0.5}
        ctx.exit_code = 1

    monkeypatch.setattr(verify_mod, "run_verify_steps", _one_step_fails)
    payload, code, artifacts = _run(monkeypatch, tmp_path / "repo")

    assert code != 0 and payload["ok"] is False
    report = _read(artifacts / "verify_report.json")
    assert report["verify_summary"] == {
        "ok": False, "failing_steps": ["ruff-gate"], "artifacts_written": report["verify_summary"]["artifacts_written"]}
    assert _read(artifacts / "index.json")["ok"] is False
    assert _gate(artifacts) == 2, "the CI baseline diff catches the success-to-failure change"


def test_a_violated_step_budget_fails_verification_and_the_report_says_so(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import mesh_cli.verify as verify_mod

    _patch_fast_success(monkeypatch)
    monkeypatch.setenv("MESH_VERIFY_BUDGET_ENFORCE", "1")
    over_budget = {
        "schema_version": 2, "ok": False, "tolerance_ms": 50, "candidates_used": [],
        "checked_steps": [{"name": "pytest-fast", "ok": False, "delta_ms": 9000}], "offenders": ["pytest-fast"],
    }
    monkeypatch.setattr(verify_mod, "_evaluate_verify_step_budget_guard",
                        lambda **_kwargs: (2, "verify slow-step budget exceeded (linux budgets): pytest-fast", over_budget))

    payload, code, artifacts = _run(monkeypatch, tmp_path / "repo")

    assert code == 2 and payload["ok"] is False
    report = _read(artifacts / "verify_report.json")
    assert report["verify_summary"]["ok"] is False, "the budget outcome is settled before the report is built"
    assert report["budgets"]["verify_step_budget"]["ok"] is False
    assert _gate(artifacts) == 2


def test_reports_and_index_are_deterministic(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_fast_success(monkeypatch)
    names = ("verify_report.json", "index.json", "verify_all_summary.json", "release_notes.json")
    runs = []
    for _ in range(2):
        _payload, code, artifacts = _run(monkeypatch, tmp_path / "repo")
        assert code == 0
        runs.append({name: (artifacts / name).read_bytes() for name in names})
        for name in names:
            (artifacts / name).unlink()
    assert runs[0] == runs[1]
