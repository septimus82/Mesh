"""F13-B (#422), end to end through ``mesh release bundle``: a bundle reusing CI's verify-all passes strict verification
(and a changed report still fails it); without ``--reuse-verify-all`` the bundle runs its own verify-all, as before.
The integration tier: each builds a real zip, release notes from git and its strict self-verification.
"""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

import tests.test_verify_all_reuse as shared
from mesh_cli import release_bundle, verify_reuse
from mesh_cli.bundle_verify import verify_zip

pytestmark = pytest.mark.integration
now, steps, _ci_verify_all = shared.now, shared.steps, shared._ci_verify_all  # (the fast file's fixtures)
UNRELATED, _with_unrelated_files = shared.UNRELATED, shared._with_unrelated_files



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
    assert "release/reports/doctor_assets.json" in names, "the run's nested reports are kept"
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
