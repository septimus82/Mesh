from __future__ import annotations

import json
from pathlib import Path

import mesh_cli


def test_release_check_orchestrates_and_writes_report(tmp_path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    calls = []

    def _stub_verify(root: Path, artifacts_dir: Path):
        calls.append(("verify", root, artifacts_dir))
        return 0, {"verify_all_summary": (artifacts_dir / "verify_all_summary.json").as_posix()}

    def _stub_assets(root: Path, out_path: Path):
        calls.append(("assets", root, out_path))
        return 0, {"asset_audit_json": out_path.as_posix()}

    def _stub_export(root: Path, out_dir: Path):
        calls.append(("export", root, out_dir))
        return 0, {"bundle_dir": out_dir.as_posix()}

    def _stub_debug(root: Path, out_path: Path):
        calls.append(("debug", root, out_path))
        return 0, {"debug_bundle_json": out_path.as_posix()}

    monkeypatch.setattr(mesh_cli.release, "_run_verify_all", _stub_verify)
    monkeypatch.setattr(mesh_cli.release, "_run_assets_audit", _stub_assets)
    monkeypatch.setattr(mesh_cli.release, "_run_export_build", _stub_export)
    monkeypatch.setattr(mesh_cli.release, "_run_debug_bundle", _stub_debug)

    assert mesh_cli.main(["release", "check", "--repo-root", str(repo_root)]) == 0
    assert [name for name, *_ in calls] == ["verify", "assets", "export", "debug"]

    release_dir = repo_root / "artifacts" / "release"
    report_path = release_dir / "release_report.json"
    summary_path = release_dir / "release_report.txt"

    assert report_path.exists()
    assert summary_path.exists()

    report = json.loads(report_path.read_text(encoding="utf-8"))
    steps = report["steps"]
    assert [step["name"] for step in steps] == ["verify-all", "asset-audit", "export-build", "debug-bundle"]
    assert report["summary"]["ok"] is True
    assert report["artifacts"]["bundle_dir"].endswith("artifacts/release/bundle")

    summary_text = summary_path.read_text(encoding="utf-8")
    assert "Result: OK" in summary_text


def test_release_check_propagates_failure_and_skips_remaining(tmp_path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    calls = []

    def _stub_verify(root: Path, artifacts_dir: Path):
        calls.append("verify")
        return 0, {"verify_all_summary": (artifacts_dir / "verify_all_summary.json").as_posix()}

    def _stub_assets(root: Path, out_path: Path):
        calls.append("assets")
        return 2, {"asset_audit_json": out_path.as_posix()}

    def _stub_export(root: Path, out_dir: Path):
        calls.append("export")
        return 0, {"bundle_dir": out_dir.as_posix()}

    def _stub_debug(root: Path, out_path: Path):
        calls.append("debug")
        return 0, {"debug_bundle_json": out_path.as_posix()}

    monkeypatch.setattr(mesh_cli.release, "_run_verify_all", _stub_verify)
    monkeypatch.setattr(mesh_cli.release, "_run_assets_audit", _stub_assets)
    monkeypatch.setattr(mesh_cli.release, "_run_export_build", _stub_export)
    monkeypatch.setattr(mesh_cli.release, "_run_debug_bundle", _stub_debug)

    assert mesh_cli.main(["release", "check", "--repo-root", str(repo_root)]) == 2
    assert calls == ["verify", "assets"]

    release_dir = repo_root / "artifacts" / "release"
    report_path = release_dir / "release_report.json"
    summary_path = release_dir / "release_report.txt"

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["summary"]["failed_step"] == "asset-audit"
    assert report["summary"]["skipped_steps"] == ["export-build", "debug-bundle"]

    summary_text = summary_path.read_text(encoding="utf-8")
    assert "FAILED at asset-audit" in summary_text
