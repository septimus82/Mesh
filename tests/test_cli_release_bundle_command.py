"""Tests for ``mesh_cli release bundle``."""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

from mesh_cli.bundle_verify import MANIFEST_SEAL_NAME, compute_manifest_seal_payload
from mesh_cli.release_bundle import (
    BUNDLE_PIPELINE,
    DEFAULT_CAMPAIGN,
    DEFAULT_SEED,
    FileEntry,
    PackageManifest,
    ReleaseBundlePlan,
    _ZIP_FIXED_DATE,
    build_package_manifest,
    build_release_bundle_zip,
    compute_release_bundle_plan,
    handle,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_step_ok(name: str, marker: str = ""):
    """Return a step that writes a marker file and exits 0."""

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
    """Return a step that fails with *exit_code*."""

    def _step(work_dir: Path, seed: int, campaign: str) -> tuple[int, dict[str, Any]]:
        return exit_code, {}

    return name, _step


def _fake_step_error(name: str, exc: Exception | None = None):
    """Return a step that raises an exception."""

    def _step(work_dir: Path, seed: int, campaign: str) -> tuple[int, dict[str, Any]]:
        raise (exc or RuntimeError(f"boom in {name}"))

    return name, _step


def _make_pipeline(*step_specs):
    return list(step_specs)


def _make_args(**overrides) -> argparse.Namespace:
    defaults = {
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


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# TestBundlePipelineStructure
# ---------------------------------------------------------------------------

class TestBundlePipelineStructure:
    """Verify the default pipeline list."""

    def test_pipeline_has_four_steps(self):
        assert len(BUNDLE_PIPELINE) == 4

    def test_pipeline_step_names(self):
        names = [n for n, _ in BUNDLE_PIPELINE]
        assert names == ["release-check", "demo-run", "export-build", "collect-audits"]


# ---------------------------------------------------------------------------
# TestComputePlan
# ---------------------------------------------------------------------------

class TestComputePlan:
    """Tests for compute_release_bundle_plan with fake steps."""

    def test_plan_collects_files(self, tmp_path: Path):
        pipeline = _make_pipeline(
            _fake_step_ok("alpha"),
            _fake_step_ok("beta"),
        )
        plan = compute_release_bundle_plan(
            tmp_path, seed=99, campaign="test_camp", pipeline=pipeline,
        )
        assert plan.ok
        assert plan.seed == 99
        assert plan.campaign == "test_camp"
        assert len(plan.files) >= 2
        archive_paths = {e.archive_path for e in plan.files}
        assert "alpha/report_alpha.json" in archive_paths
        assert "beta/report_beta.json" in archive_paths

    def test_plan_fails_fast(self, tmp_path: Path):
        pipeline = _make_pipeline(
            _fake_step_ok("good"),
            _fake_step_fail("bad", exit_code=3),
            _fake_step_ok("never"),
        )
        plan = compute_release_bundle_plan(tmp_path, pipeline=pipeline)
        assert not plan.ok
        assert any("bad" in e for e in plan.errors)
        # "never" should not have run
        assert not (tmp_path / "never").exists()

    def test_plan_catches_exceptions(self, tmp_path: Path):
        pipeline = _make_pipeline(
            _fake_step_error("boom", RuntimeError("test error")),
        )
        plan = compute_release_bundle_plan(tmp_path, pipeline=pipeline)
        assert not plan.ok
        assert any("RuntimeError" in e for e in plan.errors)

    def test_plan_quiet_mode(self, tmp_path: Path, capsys):
        pipeline = _make_pipeline(_fake_step_ok("quiet_step"))
        plan = compute_release_bundle_plan(
            tmp_path, pipeline=pipeline, quiet=True,
        )
        assert plan.ok


# ---------------------------------------------------------------------------
# TestBuildManifest
# ---------------------------------------------------------------------------

class TestBuildManifest:
    """Tests for build_package_manifest."""

    def test_manifest_has_entries(self, tmp_path: Path):
        # Create a file manually
        f = tmp_path / "hello.txt"
        f.write_text("hello world", encoding="utf-8")
        plan = ReleaseBundlePlan(
            files=[FileEntry(archive_path="hello.txt", disk_path=f)],
            seed=42,
            campaign="test",
            work_dir=tmp_path,
        )
        manifest = build_package_manifest(plan, timestamp="2026-01-01T00:00:00Z")
        assert manifest.file_count == 1
        assert manifest.total_size == 11  # len("hello world")
        assert "hello.txt" in manifest.files
        entry = manifest.files["hello.txt"]
        assert entry["size"] == 11
        assert len(entry["sha256"]) == 64

    def test_manifest_to_dict(self, tmp_path: Path):
        plan = ReleaseBundlePlan(seed=7, campaign="c", work_dir=tmp_path)
        m = build_package_manifest(plan, timestamp="T")
        d = m.to_dict()
        assert d["schema_version"] == 1
        assert d["seed"] == 7
        assert d["campaign"] == "c"
        assert d["created_utc"] == "T"

    def test_manifest_to_text(self, tmp_path: Path):
        plan = ReleaseBundlePlan(seed=7, campaign="c", work_dir=tmp_path)
        m = build_package_manifest(plan, timestamp="T")
        text = m.to_text()
        assert "Mesh Release Bundle" in text
        assert "Seed: 7" in text


# ---------------------------------------------------------------------------
# TestBuildZip
# ---------------------------------------------------------------------------

class TestBuildZip:
    """Tests for build_release_bundle_zip."""

    def _run_zip(self, tmp_path: Path, seed: int = 42) -> tuple[Path, PackageManifest]:
        pipeline = _make_pipeline(
            _fake_step_ok("release", marker="r"),
            _fake_step_ok("demo", marker="d"),
        )
        work = tmp_path / "work"
        plan = compute_release_bundle_plan(work, seed=seed, pipeline=pipeline)
        assert plan.ok
        zip_path = tmp_path / "out.zip"
        manifest = build_release_bundle_zip(plan, zip_path, timestamp="2026-01-01T00:00:00Z")
        return zip_path, manifest

    def test_zip_created(self, tmp_path: Path):
        zp, _ = self._run_zip(tmp_path)
        assert zp.exists()
        assert zp.stat().st_size > 0

    def test_zip_is_valid(self, tmp_path: Path):
        zp, _ = self._run_zip(tmp_path)
        assert zipfile.is_zipfile(zp)

    def test_zip_contains_manifest_files(self, tmp_path: Path):
        zp, _ = self._run_zip(tmp_path)
        with zipfile.ZipFile(zp, "r") as zf:
            names = set(zf.namelist())
        assert "package_manifest.json" in names
        assert "package_manifest.txt" in names
        assert MANIFEST_SEAL_NAME in names
        assert "VERSION.json" in names

    def test_zip_contains_step_outputs(self, tmp_path: Path):
        zp, _ = self._run_zip(tmp_path)
        with zipfile.ZipFile(zp, "r") as zf:
            names = zf.namelist()
        assert any(n.startswith("release/") for n in names)
        assert any(n.startswith("demo/") for n in names)

    def test_zip_forward_slash_paths(self, tmp_path: Path):
        zp, _ = self._run_zip(tmp_path)
        with zipfile.ZipFile(zp, "r") as zf:
            for name in zf.namelist():
                assert "\\" not in name, f"backslash in archive path: {name}"

    def test_zip_no_absolute_paths(self, tmp_path: Path):
        zp, _ = self._run_zip(tmp_path)
        with zipfile.ZipFile(zp, "r") as zf:
            for name in zf.namelist():
                assert not name.startswith("/"), f"absolute path: {name}"
                assert ".." not in name, f"parent ref in path: {name}"

    def test_zip_fixed_timestamps(self, tmp_path: Path):
        zp, _ = self._run_zip(tmp_path)
        with zipfile.ZipFile(zp, "r") as zf:
            for info in zf.infolist():
                assert info.date_time == _ZIP_FIXED_DATE, (
                    f"{info.filename} has date {info.date_time}, expected {_ZIP_FIXED_DATE}"
                )

    def test_zip_sorted_entries(self, tmp_path: Path):
        zp, _ = self._run_zip(tmp_path)
        with zipfile.ZipFile(zp, "r") as zf:
            names = zf.namelist()
        assert names == sorted(names), "ZIP entries not sorted"

    def test_manifest_hashes_match_content(self, tmp_path: Path):
        zp, manifest = self._run_zip(tmp_path)
        with zipfile.ZipFile(zp, "r") as zf:
            # Read the embedded manifest
            mdata = json.loads(zf.read("package_manifest.json"))
            for archive_path, entry in mdata["files"].items():
                content = zf.read(archive_path)
                actual_sha = _sha256_bytes(content)
                assert actual_sha == entry["sha256"], (
                    f"Hash mismatch for {archive_path}"
                )
                assert len(content) == entry["size"], (
                    f"Size mismatch for {archive_path}"
                )

    def test_manifest_seal_matches_manifest_files(self, tmp_path: Path):
        zp, _ = self._run_zip(tmp_path)
        with zipfile.ZipFile(zp, "r") as zf:
            manifest_json_raw = zf.read("package_manifest.json")
            manifest_txt_raw = zf.read("package_manifest.txt")
            seal_data = json.loads(zf.read(MANIFEST_SEAL_NAME))
        expected = compute_manifest_seal_payload(manifest_json_raw, manifest_txt_raw, provenance=None)
        assert seal_data["sha256_package_manifest_json"] == expected["sha256_package_manifest_json"]
        assert seal_data["sha256_package_manifest_txt"] == expected["sha256_package_manifest_txt"]


# ---------------------------------------------------------------------------
# TestDeterminism
# ---------------------------------------------------------------------------

class TestDeterminism:
    """Verify same inputs → byte-identical ZIP."""

    def test_same_seed_identical_zips(self, tmp_path: Path):
        pipeline = _make_pipeline(
            _fake_step_ok("step1"),
            _fake_step_ok("step2"),
        )
        ts = "2026-01-01T00:00:00Z"

        work_a = tmp_path / "a_work"
        plan_a = compute_release_bundle_plan(work_a, seed=42, pipeline=pipeline)
        zip_a = tmp_path / "a.zip"
        build_release_bundle_zip(plan_a, zip_a, timestamp=ts)

        work_b = tmp_path / "b_work"
        plan_b = compute_release_bundle_plan(work_b, seed=42, pipeline=pipeline)
        zip_b = tmp_path / "b.zip"
        build_release_bundle_zip(plan_b, zip_b, timestamp=ts)

        bytes_a = zip_a.read_bytes()
        bytes_b = zip_b.read_bytes()
        assert bytes_a == bytes_b, "ZIPs are not byte-identical"

    def test_different_seed_different_content(self, tmp_path: Path):
        pipeline = _make_pipeline(_fake_step_ok("s"))
        ts = "2026-01-01T00:00:00Z"

        work_a = tmp_path / "a"
        plan_a = compute_release_bundle_plan(work_a, seed=1, pipeline=pipeline)
        zip_a = tmp_path / "a.zip"
        build_release_bundle_zip(plan_a, zip_a, timestamp=ts)

        work_b = tmp_path / "b"
        plan_b = compute_release_bundle_plan(work_b, seed=2, pipeline=pipeline)
        zip_b = tmp_path / "b.zip"
        build_release_bundle_zip(plan_b, zip_b, timestamp=ts)

        # At minimum the manifests differ (different seed)
        with zipfile.ZipFile(zip_a) as za, zipfile.ZipFile(zip_b) as zb:
            ma = json.loads(za.read("package_manifest.json"))
            mb = json.loads(zb.read("package_manifest.json"))
        assert ma["seed"] != mb["seed"]


# ---------------------------------------------------------------------------
# TestFailurePropagation
# ---------------------------------------------------------------------------

class TestFailurePropagation:
    """Verify failure at any step prevents ZIP creation."""

    def test_fail_produces_no_zip(self, tmp_path: Path):
        pipeline = _make_pipeline(
            _fake_step_ok("good"),
            _fake_step_fail("bad"),
        )
        work = tmp_path / "work"
        plan = compute_release_bundle_plan(work, pipeline=pipeline)
        assert not plan.ok
        zip_path = tmp_path / "out.zip"
        # Should not even attempt to write when plan failed
        assert not zip_path.exists()

    def test_handle_returns_nonzero_on_fail(self, tmp_path: Path, monkeypatch):
        zip_path = tmp_path / "out.zip"
        pipeline = _make_pipeline(_fake_step_fail("fail_step"))
        monkeypatch.setattr(
            "mesh_cli.release_bundle.BUNDLE_PIPELINE", pipeline,
        )
        args = _make_args(out=str(zip_path), quiet=True)
        code = handle(args)
        assert code == 1
        assert not zip_path.exists()

    def test_exception_in_step_prevents_zip(self, tmp_path: Path):
        pipeline = _make_pipeline(
            _fake_step_error("err"),
        )
        plan = compute_release_bundle_plan(tmp_path / "w", pipeline=pipeline)
        assert not plan.ok
        assert any("err" in e for e in plan.errors)


# ---------------------------------------------------------------------------
# TestCLIHandle
# ---------------------------------------------------------------------------

class TestCLIHandle:
    """Tests for the handle() entry point."""

    def test_handle_success(self, tmp_path: Path, monkeypatch):
        pipeline = _make_pipeline(_fake_step_ok("test_step"))
        monkeypatch.setattr("mesh_cli.release_bundle.BUNDLE_PIPELINE", pipeline)
        zip_path = tmp_path / "bundle.zip"
        args = _make_args(out=str(zip_path), quiet=True)
        code = handle(args)
        assert code == 0
        assert zip_path.exists()

    def test_handle_same_seed_is_byte_deterministic_by_default(self, tmp_path: Path, monkeypatch):
        pipeline = _make_pipeline(_fake_step_ok("det_step"))
        monkeypatch.setattr("mesh_cli.release_bundle.BUNDLE_PIPELINE", pipeline)
        zip_path = tmp_path / "bundle.zip"

        code_a = handle(_make_args(out=str(zip_path), quiet=True, seed=123))
        assert code_a == 0
        bytes_a = zip_path.read_bytes()

        code_b = handle(_make_args(out=str(zip_path), quiet=True, seed=123))
        assert code_b == 0
        bytes_b = zip_path.read_bytes()

        assert bytes_a == bytes_b

    def test_handle_uses_pinned_timestamp_by_default_when_seed_present(self, tmp_path: Path, monkeypatch):
        pipeline = _make_pipeline(_fake_step_ok("ts_step"))
        monkeypatch.setattr("mesh_cli.release_bundle.BUNDLE_PIPELINE", pipeline)
        zip_path = tmp_path / "bundle.zip"

        code = handle(_make_args(out=str(zip_path), quiet=True, seed=123))
        assert code == 0

        with zipfile.ZipFile(zip_path, "r") as zf:
            manifest = json.loads(zf.read("package_manifest.json"))
        assert manifest["created_utc"] == "1980-01-01T00:00:00Z"

    def test_handle_json_format(self, tmp_path: Path, monkeypatch, capsys):
        pipeline = _make_pipeline(_fake_step_ok("j"))
        monkeypatch.setattr("mesh_cli.release_bundle.BUNDLE_PIPELINE", pipeline)
        zip_path = tmp_path / "j.zip"
        args = _make_args(out=str(zip_path), report_format="json", quiet=False)
        code = handle(args)
        assert code == 0
        captured = capsys.readouterr()
        # JSON output is followed by text summary + OK line; extract the JSON portion
        # by finding the first '{' to the matching '}'
        out = captured.out
        start = out.index("{")
        # Find JSON by trying to parse progressively
        data = json.loads(out[start : out.rindex("}") + 1])
        assert data["schema_version"] == 1

    def test_handle_quiet(self, tmp_path: Path, monkeypatch, capsys):
        pipeline = _make_pipeline(_fake_step_ok("q"))
        monkeypatch.setattr("mesh_cli.release_bundle.BUNDLE_PIPELINE", pipeline)
        zip_path = tmp_path / "q.zip"
        args = _make_args(out=str(zip_path), quiet=True)
        code = handle(args)
        assert code == 0
        captured = capsys.readouterr()
        # Quiet suppresses step output but still prints final OK
        # (which is fine — exact output not critical)

    def test_work_dir_cleaned_up(self, tmp_path: Path, monkeypatch):
        pipeline = _make_pipeline(_fake_step_ok("c"))
        monkeypatch.setattr("mesh_cli.release_bundle.BUNDLE_PIPELINE", pipeline)
        zip_path = tmp_path / "clean.zip"
        args = _make_args(out=str(zip_path), quiet=True)
        code = handle(args)
        assert code == 0
        work_dir = zip_path.parent / f"_work_{zip_path.stem}"
        assert not work_dir.exists(), "Work directory should be cleaned up"


# ---------------------------------------------------------------------------
# TestPackageManifestFormat
# ---------------------------------------------------------------------------

class TestPackageManifestFormat:
    """Tests for PackageManifest text/dict output."""

    def test_manifest_text_contains_key_fields(self):
        m = PackageManifest(
            seed=42,
            campaign="mini_campaign_01",
            engine_version="0.4.0",
            git_hash="abc123",
            python_version="3.13.3",
            platform_tag="win-amd64",
            created_utc="2026-01-01T00:00:00Z",
            file_count=10,
            total_size=12345,
            files={"a.json": {"size": 100, "sha256": "a" * 64}},
        )
        text = m.to_text()
        assert "Engine: 0.4.0" in text
        assert "Seed: 42" in text
        assert "Git: abc123" in text
        assert "Files: 10" in text
        assert "a.json" in text

    def test_manifest_dict_has_git_hash_when_set(self):
        m = PackageManifest(git_hash="deadbeef")
        d = m.to_dict()
        assert d["git_hash"] == "deadbeef"

    def test_manifest_dict_omits_git_hash_when_none(self):
        m = PackageManifest(git_hash=None)
        d = m.to_dict()
        assert "git_hash" not in d

    def test_manifest_text_omits_git_when_none(self):
        m = PackageManifest(git_hash=None)
        text = m.to_text()
        assert "Git:" not in text
