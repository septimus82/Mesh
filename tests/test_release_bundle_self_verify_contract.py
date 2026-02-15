"""Tests for release bundle self-verification (Phase 14).

Covers:
- Success path: ZIP contains verify reports with correct hashes
- Failure path: monkeypatched verifier causes exit 1, ZIP deleted
- Determinism: two runs with same seed produce byte-identical ZIPs
"""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

from mesh_cli.release_bundle import (
    DEFAULT_CAMPAIGN,
    DEFAULT_SEED,
    FileEntry,
    PackageManifest,
    ReleaseBundlePlan,
    build_package_manifest,
    build_release_bundle_zip,
    handle,
    self_verify_and_embed,
)
from mesh_cli.bundle_verify import MANIFEST_SEAL_NAME


# ---------------------------------------------------------------------------
# Helpers — identical pattern to existing release bundle tests
# ---------------------------------------------------------------------------

def _fake_step_ok(name: str, marker: str = ""):
    def _step(work_dir: Path, seed: int, campaign: str) -> tuple[int, dict[str, Any]]:
        out = work_dir / name
        out.mkdir(parents=True, exist_ok=True)
        (out / f"report_{name}.json").write_text(
            json.dumps({"name": name, "seed": seed, "campaign": campaign, "marker": marker}),
            encoding="utf-8",
        )
        return 0, {"dir": f"{name}/"}
    return name, _step


def _fake_step_fail(name: str, exit_code: int = 1):
    def _step(work_dir: Path, seed: int, campaign: str) -> tuple[int, dict[str, Any]]:
        return exit_code, {}
    return name, _step


def _make_pipeline(*step_specs: Any) -> list[Any]:
    return list(step_specs)


def _make_args(**overrides: Any) -> argparse.Namespace:
    defaults: dict[str, Any] = {
        "command": "release",
        "release_command": "bundle",
        "out": "release_bundle.zip",
        "seed": DEFAULT_SEED,
        "campaign": DEFAULT_CAMPAIGN,
        "report_format": "text",
        "quiet": False,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------

class TestSelfVerifySuccess:
    """After handle(), the ZIP must contain self-verify reports."""

    def test_zip_contains_verify_reports(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        pipeline = _make_pipeline(_fake_step_ok("s1"), _fake_step_ok("s2"))
        monkeypatch.setattr("mesh_cli.release_bundle.BUNDLE_PIPELINE", pipeline)
        zip_path = tmp_path / "bundle.zip"
        code = handle(_make_args(out=str(zip_path), quiet=True))
        assert code == 0
        assert zip_path.exists()

        with zipfile.ZipFile(zip_path, "r") as zf:
            names = set(zf.namelist())
            assert "verify/verify_report.json" in names
            assert "verify/verify_report.txt" in names
            assert MANIFEST_SEAL_NAME in names

    def test_verify_report_json_is_valid(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        pipeline = _make_pipeline(_fake_step_ok("v"))
        monkeypatch.setattr("mesh_cli.release_bundle.BUNDLE_PIPELINE", pipeline)
        zip_path = tmp_path / "bundle.zip"
        handle(_make_args(out=str(zip_path), quiet=True))

        with zipfile.ZipFile(zip_path, "r") as zf:
            data = json.loads(zf.read("verify/verify_report.json"))
            assert data["ok"] is True
            assert data["sealed_manifest_verified"] is True
            assert data["counts"]["extra_files"] == 0
            assert data["counts"]["missing_files"] == 0
            assert data["counts"]["hash_mismatches"] == 0
            assert data["counts"]["verified_files"] > 0
            assert data["counts"]["verified_files"] == data["counts"]["verifiable_files"]
            assert data["counts"]["sealed_manifest_files"] == 2
            assert data["counts"]["skipped_files"] == 0
            assert data["missing"] == []
            assert data["extras"] == []
            assert data["mismatches"] == []
            assert data["skipped"] == []
            assert len(data["errors"]) == 0

    def test_verify_report_has_no_absolute_paths(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        pipeline = _make_pipeline(_fake_step_ok("p"))
        monkeypatch.setattr("mesh_cli.release_bundle.BUNDLE_PIPELINE", pipeline)
        zip_path = tmp_path / "bundle.zip"
        handle(_make_args(out=str(zip_path), quiet=True))

        with zipfile.ZipFile(zip_path, "r") as zf:
            data = json.loads(zf.read("verify/verify_report.json"))
            # The 'zip' field should be just the filename, not an absolute path
            assert "/" not in data["zip"] and "\\" not in data["zip"]

    def test_manifest_includes_verify_file_hashes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        pipeline = _make_pipeline(_fake_step_ok("m"))
        monkeypatch.setattr("mesh_cli.release_bundle.BUNDLE_PIPELINE", pipeline)
        zip_path = tmp_path / "bundle.zip"
        handle(_make_args(out=str(zip_path), quiet=True))

        with zipfile.ZipFile(zip_path, "r") as zf:
            manifest = json.loads(zf.read("package_manifest.json"))
            files = manifest["files"]
            assert "verify/verify_report.json" in files
            assert "verify/verify_report.txt" in files

            # Verify hashes match actual content
            for vpath in ("verify/verify_report.json", "verify/verify_report.txt"):
                expected_sha = files[vpath]["sha256"]
                actual_sha = _sha256(zf.read(vpath))
                assert actual_sha == expected_sha, f"Hash mismatch for {vpath}"

    def test_external_verify_passes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """The produced ZIP passes an independent `bundle verify`."""
        from mesh_cli.bundle_verify import verify_zip

        pipeline = _make_pipeline(_fake_step_ok("x"))
        monkeypatch.setattr("mesh_cli.release_bundle.BUNDLE_PIPELINE", pipeline)
        zip_path = tmp_path / "bundle.zip"
        handle(_make_args(out=str(zip_path), quiet=True))

        report = verify_zip(str(zip_path))
        assert report["ok"] is True, f"Errors: {report['errors']}"

    def test_verify_txt_contains_ok(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        pipeline = _make_pipeline(_fake_step_ok("t"))
        monkeypatch.setattr("mesh_cli.release_bundle.BUNDLE_PIPELINE", pipeline)
        zip_path = tmp_path / "bundle.zip"
        handle(_make_args(out=str(zip_path), quiet=True))

        with zipfile.ZipFile(zip_path, "r") as zf:
            txt = zf.read("verify/verify_report.txt").decode("utf-8")
            assert "OK" in txt


# ---------------------------------------------------------------------------
# Failure path
# ---------------------------------------------------------------------------

class TestSelfVerifyFailure:
    """If verification fails, ZIP is deleted and exit code is 1."""

    def test_monkeypatched_verify_causes_exit_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pipeline = _make_pipeline(_fake_step_ok("f"))
        monkeypatch.setattr("mesh_cli.release_bundle.BUNDLE_PIPELINE", pipeline)

        # Monkeypatch verify_zip to always report failure
        def _bad_verify(zip_path: str, *, options: Any | None = None) -> dict[str, Any]:
            return {
                "zip": zip_path,
                "ok": False,
                "errors": ["Injected failure"],
                "warnings": [],
                "file_count": 0,
                "verified_count": 0,
            }

        monkeypatch.setattr("mesh_cli.release_bundle.self_verify_and_embed.__module__", "mesh_cli.release_bundle")
        # Patch verify_zip where it's imported in self_verify_and_embed
        monkeypatch.setattr("mesh_cli.bundle_verify.verify_zip", _bad_verify)

        zip_path = tmp_path / "bad.zip"
        code = handle(_make_args(out=str(zip_path), quiet=True))
        assert code == 1
        assert not zip_path.exists(), "ZIP should be deleted on verification failure"

    def test_failure_leaves_debug_report(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pipeline = _make_pipeline(_fake_step_ok("dbg"))
        monkeypatch.setattr("mesh_cli.release_bundle.BUNDLE_PIPELINE", pipeline)

        def _bad_verify(zip_path: str, *, options: Any | None = None) -> dict[str, Any]:
            return {
                "zip": zip_path,
                "ok": False,
                "errors": ["Injected corruption"],
                "warnings": [],
                "file_count": 1,
                "verified_count": 0,
            }

        monkeypatch.setattr("mesh_cli.bundle_verify.verify_zip", _bad_verify)

        zip_path = tmp_path / "dbg.zip"
        handle(_make_args(out=str(zip_path), quiet=True))

        # Debug report should be next to where the ZIP would have been
        fail_json = tmp_path / "verify_report_FAILED.json"
        assert fail_json.exists()
        data = json.loads(fail_json.read_text(encoding="utf-8"))
        assert data["ok"] is False
        assert "Injected corruption" in data["errors"]


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestSelfVerifyDeterminism:
    """Two runs with the same seed produce byte-identical ZIPs."""

    def test_identical_zips(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from mesh_cli.release_bundle import compute_release_bundle_plan

        pipeline = _make_pipeline(_fake_step_ok("d1"), _fake_step_ok("d2"))
        ts = "2026-01-01T00:00:00Z"

        # Also pin provenance so timestamps inside it are stable
        from engine.provenance import Provenance, provenance_to_dict

        fixed_prov = provenance_to_dict(Provenance(
            tool_name="Mesh Engine",
            tool_version="0.4.0",
            python_version="3.13.3",
            platform="win32",
        ))
        monkeypatch.setattr(
            "mesh_cli.release_bundle.provenance_to_dict",
            lambda _prov: fixed_prov,
        )

        # Run A
        work_a = tmp_path / "a_work"
        plan_a = compute_release_bundle_plan(work_a, seed=99, pipeline=pipeline)
        zip_a = tmp_path / "a.zip"
        build_release_bundle_zip(plan_a, zip_a, timestamp=ts)
        self_verify_and_embed(
            zip_path=zip_a, work_dir=work_a, plan=plan_a,
            timestamp=ts, quiet=True,
        )

        # Run B
        work_b = tmp_path / "b_work"
        plan_b = compute_release_bundle_plan(work_b, seed=99, pipeline=pipeline)
        zip_b = tmp_path / "b.zip"
        build_release_bundle_zip(plan_b, zip_b, timestamp=ts)
        self_verify_and_embed(
            zip_path=zip_b, work_dir=work_b, plan=plan_b,
            timestamp=ts, quiet=True,
        )

        bytes_a = zip_a.read_bytes()
        bytes_b = zip_b.read_bytes()
        assert bytes_a == bytes_b, "Two runs with same seed should produce identical ZIPs"


# ---------------------------------------------------------------------------
# self_verify_and_embed direct tests
# ---------------------------------------------------------------------------

class TestSelfVerifyAndEmbed:
    """Unit tests for self_verify_and_embed()."""

    def test_returns_zero_on_valid_zip(self, tmp_path: Path) -> None:
        # Build a mini ZIP via the build function
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        (work_dir / "data.txt").write_text("hello", encoding="utf-8")

        plan = ReleaseBundlePlan(
            seed=42,
            campaign="test",
            work_dir=work_dir,
            files=[FileEntry(archive_path="data.txt", disk_path=work_dir / "data.txt")],
        )

        zip_path = tmp_path / "test.zip"
        build_release_bundle_zip(plan, zip_path, timestamp="2026-01-01T00:00:00Z")

        rc = self_verify_and_embed(
            zip_path=zip_path,
            work_dir=work_dir,
            plan=plan,
            timestamp="2026-01-01T00:00:00Z",
            quiet=True,
        )
        assert rc == 0

        # Verify the rebuild included verify reports
        with zipfile.ZipFile(zip_path, "r") as zf:
            assert "verify/verify_report.json" in zf.namelist()
            assert "verify/verify_report.txt" in zf.namelist()

    def test_returns_one_on_bad_zip(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        (work_dir / "data.txt").write_text("hello", encoding="utf-8")

        plan = ReleaseBundlePlan(
            seed=42, campaign="test", work_dir=work_dir,
            files=[FileEntry(archive_path="data.txt", disk_path=work_dir / "data.txt")],
        )

        zip_path = tmp_path / "test.zip"
        build_release_bundle_zip(plan, zip_path, timestamp="2026-01-01T00:00:00Z")

        def _bad_verify(zp: str, *, options: Any | None = None) -> dict[str, Any]:
            return {"zip": zp, "ok": False, "errors": ["bad"], "warnings": [], "file_count": 0, "verified_count": 0}

        monkeypatch.setattr("mesh_cli.bundle_verify.verify_zip", _bad_verify)

        rc = self_verify_and_embed(
            zip_path=zip_path, work_dir=work_dir, plan=plan,
            timestamp="2026-01-01T00:00:00Z", quiet=True,
        )
        assert rc == 1
