"""F13-B (#422), through the release check and ``mesh release bundle`` (the integration tier: each runs the real
release-check handler, writing its reports, or builds a real zip with release notes from git and strict self-verification).

The release check reuses CI's verify-all only on proof and still runs its asset audit, export build and debug bundle; a
refused or interrupted reuse falls back to running verify-all, and one that can't be undone fails it. A reusing bundle
passes strict verification, keeps out files verify-all didn't produce, and fails strict verification when tampered
with; without ``--reuse-verify-all`` the bundle runs its own verify-all, as before. The decisions themselves are in
tests/test_verify_all_reuse.py (fast).
"""

from __future__ import annotations

import argparse
import json
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

import mesh_cli.release as release
import tests.test_verify_all_reuse as shared
from mesh_cli import release_bundle, verify_reuse
from mesh_cli.bundle_verify import verify_zip
from mesh_cli.release_check_pipeline import _write_deterministic_verify_all_summary

pytestmark = pytest.mark.integration
now, _ci_verify_all = shared.now, shared._ci_verify_all  # (the fast file's fixture and helpers)
_summary, _write_reports, _failing_copy = shared._summary, shared._write_reports, shared._failing_copy
UNRELATED, _with_unrelated_files = shared.UNRELATED, shared._with_unrelated_files



# --------------------------------------------------------------------- the release check

@pytest.fixture
def steps(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[str]]:
    """The release check's four steps replaced by recorders (the real ones run verify-all, an export, a debug
    bundle); verify-all writes the same reports as CI's, deterministically, as the real ``_run_verify_all``."""
    calls: dict[str, list[str]] = {"verify-all": [], "asset-audit": [], "export-build": [], "debug-bundle": []}

    def verify_all(repo_root: Path, artifacts_dir: Path, *, deterministic: bool = False) -> tuple[int, dict[str, Any]]:
        calls["verify-all"].append(str(artifacts_dir))
        _write_reports(artifacts_dir, _summary())
        _write_deterministic_verify_all_summary(artifacts_dir, _summary())
        return 0, {"verify_all_ok": True, "verify_all_summary": (artifacts_dir / "verify_all_summary.json").as_posix()}

    def recorder(name: str) -> Callable[..., tuple[int, dict[str, Any]]]:
        def run(_repo_root: Path, out: Path, **_kw: Any) -> tuple[int, dict[str, Any]]:
            calls[name].append(str(out))
            return 0, {}
        return run

    monkeypatch.setattr(release, "_run_verify_all", verify_all)
    monkeypatch.setattr(release, "_run_assets_audit", recorder("asset-audit"))
    monkeypatch.setattr(release, "_run_export_build", recorder("export-build"))
    monkeypatch.setattr(release, "_run_debug_bundle", recorder("debug-bundle"))
    return calls


def _release_check(release_dir: Path, reuse_from: Path | None) -> int:
    return release._handle_check(argparse.Namespace(
        command="release", release_command="check", repo_root=".", artifacts=str(release_dir), report=None,
        summary=None, deterministic=True, quiet=True, reuse_verify_all=str(reuse_from) if reuse_from else None))


def test_the_release_check_reuses_verify_all_and_still_runs_its_other_steps(tmp_path: Path, now: dict[str, Any],
                                                                            steps: dict[str, list[str]]) -> None:
    source = _ci_verify_all(tmp_path / "artifacts")
    assert _release_check(tmp_path / "release", source) == 0
    assert steps["verify-all"] == [], "not run a second time"
    assert all(len(steps[name]) == 1 for name in ("asset-audit", "export-build", "debug-bundle"))
    report = json.loads((tmp_path / "release/release_report.json").read_text(encoding="utf-8"))
    verify_step = next(s for s in report["steps"] if s["name"] == "verify-all")
    assert verify_step["ok"] and verify_step["outputs"]["verify_all_reused_from"] == "artifacts"


def test_refused_evidence_means_the_release_check_runs_verify_all_itself(tmp_path: Path, now: dict[str, Any],
                                                                         steps: dict[str, list[str]]) -> None:
    source = _ci_verify_all(tmp_path / "artifacts", exit_code=1, ok=False)
    assert _release_check(tmp_path / "release", source) == 0
    assert steps["verify-all"] == [str(tmp_path / "release")], "run here, as before"
    record = json.loads((tmp_path / "release" / verify_reuse.RECORD).read_text(encoding="utf-8"))
    assert record["reused"] is False and "didn't pass" in record["reason"]


def test_an_interrupted_copy_falls_back_to_running_verify_all(tmp_path: Path, now: dict[str, Any],
                                                               steps: dict[str, list[str]],
                                                               monkeypatch: pytest.MonkeyPatch) -> None:
    source = _ci_verify_all(tmp_path / "artifacts")
    _failing_copy(monkeypatch, at="verify_summary.txt")
    assert _release_check(tmp_path / "release", source) == 0
    assert steps["verify-all"] == [str(tmp_path / "release")], "run here instead"
    record = json.loads((tmp_path / "release" / verify_reuse.RECORD).read_text(encoding="utf-8"))
    assert record["reused"] is False and "couldn't be copied" in record["reason"]


def test_a_reuse_that_cannot_be_undone_fails_the_release_check(tmp_path: Path, now: dict[str, Any],
                                                               steps: dict[str, list[str]],
                                                               monkeypatch: pytest.MonkeyPatch) -> None:
    """A partial copy that can't be removed would end up in the bundle: the release check fails instead."""
    source = _ci_verify_all(tmp_path / "artifacts")
    _failing_copy(monkeypatch, at="verify_summary.txt")

    def stuck(path: Path) -> None:
        raise PermissionError(13, "in use", str(path))

    monkeypatch.setattr(verify_reuse, "_remove", stuck)
    assert _release_check(tmp_path / "release", source) != 0
    assert steps["verify-all"] == [] and steps["export-build"] == [], "stopped at verify-all"
    record = json.loads((tmp_path / "release" / verify_reuse.RECORD).read_text(encoding="utf-8"))
    assert record["reused"] is False and "couldn't be undone" in record["reason"]


@pytest.mark.parametrize("failing", ["asset-audit", "export-build", "debug-bundle"])
def test_a_failing_audit_export_or_debug_step_still_fails_a_reusing_release_check(
        tmp_path: Path, now: dict[str, Any], steps: dict[str, list[str]], monkeypatch: pytest.MonkeyPatch,
        failing: str) -> None:
    name = {"asset-audit": "_run_assets_audit", "export-build": "_run_export_build",
            "debug-bundle": "_run_debug_bundle"}[failing]
    monkeypatch.setattr(release, name, lambda *_a, **_k: (1, {}))
    assert _release_check(tmp_path / "release", _ci_verify_all(tmp_path / "artifacts")) != 0
    report = json.loads((tmp_path / "release/release_report.json").read_text(encoding="utf-8"))
    assert report["summary"]["failed_step"] == failing and steps["verify-all"] == []


def test_reused_and_rerun_release_reports_differ_only_where_documented(tmp_path: Path, now: dict[str, Any],
                                                                       steps: dict[str, list[str]]) -> None:
    """The same reports either way, byte for byte, apart from the reuse record and the release report's note of
    where verify-all came from; CI's extras (index, report, overlay perf, release notes) aren't copied."""
    rerun_dir, reused_dir = tmp_path / "a" / "release", tmp_path / "b" / "release"
    assert _release_check(rerun_dir, None) == 0
    assert _release_check(reused_dir, _ci_verify_all(tmp_path / "artifacts")) == 0
    rerun = {p.relative_to(rerun_dir).as_posix(): p.read_bytes() for p in rerun_dir.rglob("*") if p.is_file()}
    reused = {p.relative_to(reused_dir).as_posix(): p.read_bytes() for p in reused_dir.rglob("*") if p.is_file()}
    assert set(reused) == set(rerun) | {verify_reuse.RECORD}
    assert sorted(rel for rel in rerun if rerun[rel] != reused[rel]) == ["release_report.json"]
    rerun_report, reused_report = (json.loads(d["release_report.json"]) for d in (rerun, reused))
    reused_step = next(s for s in reused_report["steps"] if s["name"] == "verify-all")
    assert reused_step["outputs"].pop("verify_all_reused_from") == "artifacts"
    assert reused_report == rerun_report, "the only difference: where verify-all's reports came from"


# --------------------------------------------------------------------- the bundle

def _bundle_args(out: Path, reuse_from: Path | None) -> argparse.Namespace:
    return argparse.Namespace(command="release", release_command="bundle", out=str(out), seed=123,
                              campaign=release_bundle.DEFAULT_CAMPAIGN, report_format="text", quiet=True,
                              reuse_verify_all=str(reuse_from) if reuse_from else None)


def test_a_bundle_reusing_verify_all_passes_strict_verification_and_tampering_fails_it(
        tmp_path: Path, now: dict[str, Any], steps: dict[str, list[str]], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(release_bundle, "BUNDLE_PIPELINE", [("release-check", release_bundle._step_release_check)])
    zip_path = tmp_path / "out" / "release_bundle.zip"
    source = tmp_path / "artifacts"
    _with_unrelated_files(source)  # (an older summary, notes, an archive, a nested stray file)
    assert release_bundle.handle(_bundle_args(zip_path, _ci_verify_all(source))) == 0
    assert steps["verify-all"] == [] and len(steps["export-build"]) == 1
    with zipfile.ZipFile(zip_path) as bundle:
        names = bundle.namelist()
        record = json.loads(bundle.read(f"release/{verify_reuse.RECORD}"))
    assert "release/verify_summary.txt" in names and "release/pytest_fast.log" not in names and record["reused"] is True
    assert f"release/{shared.NESTED}" in names and f"release/{shared.SCRATCH_FILE}" in names, "nested ones kept"
    strays = [n for n in names if any(n.endswith(rel) for rel in UNRELATED)]
    assert strays == [], f"files the run didn't produce reached the bundle: {strays}"
    assert verify_zip(str(zip_path))["ok"] is True
    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(zip_path) as src, zipfile.ZipFile(tampered, "w") as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            dst.writestr(info, b'{"ok": true, "forged": true}\n' if info.filename == "release/verify_all_summary.json" else data)
    report = verify_zip(str(tampered))
    assert report["ok"] is False and report["errors"], "strict verification still catches a changed report"


def test_a_bundle_without_the_option_runs_its_own_verify_all(tmp_path: Path, now: dict[str, Any],
                                                             steps: dict[str, list[str]],
                                                             monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(release_bundle, "BUNDLE_PIPELINE", [("release-check", release_bundle._step_release_check)])
    _ci_verify_all(tmp_path / "artifacts")  # (evidence lying around is never used unless asked for)
    zip_path = tmp_path / "out" / "release_bundle.zip"
    assert release_bundle.handle(_bundle_args(zip_path, None)) == 0
    assert len(steps["verify-all"]) == 1
    with zipfile.ZipFile(zip_path) as bundle:
        assert f"release/{verify_reuse.RECORD}" not in bundle.namelist()
