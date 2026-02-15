"""Tests for ``mesh_cli bundle verify`` command."""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

from mesh_cli.bundle_verify import (
    MANIFEST_NAME,
    MANIFEST_SEAL_NAME,
    MANIFEST_TEXT_NAME,
    ExcludeRule,
    VerifyOptions,
    compute_manifest_seal_payload,
    handle,
    register,
    verify_zip,
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _make_args(**overrides: object) -> argparse.Namespace:
    defaults: dict[str, Any] = {
        "command": "bundle",
        "bundle_command": "verify",
        "zip": "test.zip",
        "zip_opt": None,
        "verify_json": False,
        "verify_strict": True,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _manifest_json_bytes(manifest: dict[str, Any]) -> bytes:
    return (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _seal_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _build_valid_zip(
    zip_path: Path,
    files: dict[str, bytes] | None = None,
    *,
    add_dir_entry: bool = False,
    extra_files: dict[str, bytes] | None = None,
) -> None:
    if files is None:
        files = {
            "data/hello.txt": b"hello world",
            "data/config.json": b'{"key": "value"}',
        }

    manifest_txt_bytes = b"Mesh package manifest text\n"
    seal_payload: dict[str, Any] = {
        "schema_version": 1,
        "mode": "manifest_projection_v1",
        "sha256_package_manifest_json": "",
        "sha256_package_manifest_txt": "",
        "size_package_manifest_json": 0,
        "size_package_manifest_txt": len(manifest_txt_bytes),
    }
    seal_bytes = _seal_bytes(seal_payload)

    # Iterate to stable seal payload with projected manifest hashing.
    for _ in range(6):
        manifest_files: dict[str, dict[str, Any]] = {
            name: {"size": len(content), "sha256": _sha256(content)}
            for name, content in files.items()
        }
        manifest_files[MANIFEST_SEAL_NAME] = {
            "size": len(seal_bytes),
            "sha256": _sha256(seal_bytes),
        }

        manifest = {
            "schema_version": 1,
            "files": manifest_files,
        }
        manifest_json_bytes = _manifest_json_bytes(manifest)
        next_payload = compute_manifest_seal_payload(manifest_json_bytes, manifest_txt_bytes, provenance=None)
        next_seal_bytes = _seal_bytes(next_payload)
        if next_seal_bytes == seal_bytes:
            break
        seal_bytes = next_seal_bytes

    # Final manifest pass with stabilized seal bytes.
    manifest_files = {
        name: {"size": len(content), "sha256": _sha256(content)}
        for name, content in files.items()
    }
    manifest_files[MANIFEST_SEAL_NAME] = {
        "size": len(seal_bytes),
        "sha256": _sha256(seal_bytes),
    }
    manifest = {
        "schema_version": 1,
        "files": manifest_files,
    }
    manifest_json_bytes = _manifest_json_bytes(manifest)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        if add_dir_entry:
            zf.writestr("data/", b"")
        for name, content in files.items():
            zf.writestr(name, content)
        zf.writestr(MANIFEST_SEAL_NAME, seal_bytes)
        zf.writestr(MANIFEST_NAME, manifest_json_bytes)
        zf.writestr(MANIFEST_TEXT_NAME, manifest_txt_bytes)
        for name, content in (extra_files or {}).items():
            zf.writestr(name, content)


class TestBundleVerifyOK:
    def test_ok_exit_code(self, tmp_path: Path) -> None:
        zp = tmp_path / "good.zip"
        _build_valid_zip(zp)
        rc = handle(_make_args(zip=str(zp)))
        assert rc == 0

    def test_ok_json_has_complete_counts(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        zp = tmp_path / "good.zip"
        _build_valid_zip(zp)
        rc = handle(_make_args(zip=str(zp), verify_json=True))
        assert rc == 0

        data = json.loads(capsys.readouterr().out)
        assert data["ok"] is True
        assert data["strict"] is True
        assert data["sealed_manifest_verified"] is True
        assert data["counts"]["extra_files"] == 0
        assert data["counts"]["missing_files"] == 0
        assert data["counts"]["hash_mismatches"] == 0
        assert data["counts"]["skipped_files"] == 0
        assert data["counts"]["sealed_manifest_files"] == 2
        assert data["counts"]["verified_files"] == data["counts"]["verifiable_files"]
        assert data["extras"] == []
        assert data["missing"] == []
        assert data["mismatches"] == []


class TestBundleVerifyFailures:
    def test_missing_file(self, tmp_path: Path) -> None:
        zp = tmp_path / "missing.zip"
        rc = handle(_make_args(zip=str(zp)))
        assert rc == 1

    def test_not_a_zip(self, tmp_path: Path) -> None:
        zp = tmp_path / "bad.zip"
        zp.write_bytes(b"not a zip at all")
        rc = handle(_make_args(zip=str(zp)))
        assert rc == 1

    def test_no_manifest(self, tmp_path: Path) -> None:
        zp = tmp_path / "noman.zip"
        with zipfile.ZipFile(zp, "w") as zf:
            zf.writestr("file.txt", "hello")
        rc = handle(_make_args(zip=str(zp)))
        assert rc == 1

    def test_missing_seal_fails_in_strict_mode(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        zp = tmp_path / "noseal.zip"
        _build_valid_zip(zp)

        with zipfile.ZipFile(zp, "r") as zf:
            kept = {name: zf.read(name) for name in zf.namelist() if name != MANIFEST_SEAL_NAME}
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as zf:
            for name in sorted(kept.keys()):
                zf.writestr(name, kept[name])

        rc = handle(_make_args(zip=str(zp), verify_json=True))
        assert rc == 1
        data = json.loads(capsys.readouterr().out)
        assert any(MANIFEST_SEAL_NAME in err for err in data["errors"])

    def test_corrupt_manifest_file_fails_seal(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        zp = tmp_path / "corrupt_manifest.zip"
        _build_valid_zip(zp)

        with zipfile.ZipFile(zp, "r") as zf:
            payloads = {name: zf.read(name) for name in zf.namelist()}
        payloads[MANIFEST_TEXT_NAME] = b"tampered manifest text\n"
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as zf:
            for name in sorted(payloads.keys()):
                zf.writestr(name, payloads[name])

        rc = handle(_make_args(zip=str(zp), verify_json=True))
        assert rc == 1
        data = json.loads(capsys.readouterr().out)
        assert any("Manifest seal mismatch for package_manifest.txt" in err for err in data["errors"])

    def test_corrupt_seal_fails(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        zp = tmp_path / "corrupt_seal.zip"
        _build_valid_zip(zp)

        with zipfile.ZipFile(zp, "r") as zf:
            payloads = {name: zf.read(name) for name in zf.namelist()}
        payloads[MANIFEST_SEAL_NAME] = b"{}\n"
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as zf:
            for name in sorted(payloads.keys()):
                zf.writestr(name, payloads[name])

        rc = handle(_make_args(zip=str(zp), verify_json=True))
        assert rc == 1
        data = json.loads(capsys.readouterr().out)
        assert any("Manifest seal mismatch" in err or MANIFEST_SEAL_NAME in err for err in data["errors"])


class TestCoverageModes:
    def test_directory_entries_are_counted_separately(self, tmp_path: Path) -> None:
        zp = tmp_path / "dirs.zip"
        _build_valid_zip(zp, add_dir_entry=True)

        report = verify_zip(str(zp), options=VerifyOptions(strict=True, exclude=()))
        assert report["ok"] is True
        assert report["counts"]["directory_entries"] == 1
        assert report["counts"]["total_zip_entries"] == 6
        assert report["counts"]["verifiable_files"] == 5
        assert report["counts"]["verified_files"] == 5
        assert report["counts"]["skipped_files"] == 0
        assert report["extras"] == []

    def test_strict_mode_fails_on_extra_file(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        zp = tmp_path / "extra_strict.zip"
        _build_valid_zip(zp, extra_files={"bonus.txt": b"sneaky"})

        rc = handle(_make_args(zip=str(zp), verify_json=True))
        assert rc == 1
        data = json.loads(capsys.readouterr().out)
        assert data["counts"]["extra_files"] == 1
        assert data["extras"] == ["bonus.txt"]
        assert any("Strict coverage failed" in e for e in data["errors"])

    def test_non_strict_mode_reports_extra_file(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        zp = tmp_path / "extra_nonstrict.zip"
        _build_valid_zip(zp, extra_files={"bonus.txt": b"sneaky"})

        rc = handle(_make_args(zip=str(zp), verify_json=True, verify_strict=False))
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["ok"] is True
        assert data["strict"] is False
        assert data["counts"]["extra_files"] == 1
        assert data["extras"] == ["bonus.txt"]

    def test_exclusion_rule_reports_reason(self, tmp_path: Path) -> None:
        zp = tmp_path / "excluded.zip"
        _build_valid_zip(zp, extra_files={"meta/.DS_Store": b"metadata"})

        options = VerifyOptions(
            strict=True,
            exclude=(ExcludeRule(pattern="meta/.DS_Store", reason="os metadata"),),
        )
        report = verify_zip(str(zp), options=options)
        assert report["ok"] is True
        assert report["counts"]["skipped_files"] == 1
        assert report["skipped"] == [{"path": "meta/.DS_Store", "reason": "os metadata"}]
        assert report["extras"] == []


class TestPathSafety:
    def test_absolute_path_error(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        zp = tmp_path / "abs.zip"
        content = b"data"
        manifest = {
            "schema_version": 1,
            "files": {
                "/etc/passwd": {"size": len(content), "sha256": _sha256(content)},
                MANIFEST_SEAL_NAME: {"size": 2, "sha256": _sha256(b"{}")},
            },
        }
        with zipfile.ZipFile(zp, "w") as zf:
            zf.writestr("/etc/passwd", content)
            zf.writestr(MANIFEST_SEAL_NAME, b"{}")
            zf.writestr(MANIFEST_NAME, _manifest_json_bytes(manifest))
            zf.writestr(MANIFEST_TEXT_NAME, b"text\n")
        rc = handle(_make_args(zip=str(zp), verify_json=True))
        assert rc == 1
        data = json.loads(capsys.readouterr().out)
        assert any("Absolute path" in e for e in data["errors"])

    def test_path_traversal_error(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        zp = tmp_path / "traverse.zip"
        content = b"data"
        manifest = {
            "schema_version": 1,
            "files": {
                "../secret.txt": {"size": len(content), "sha256": _sha256(content)},
                MANIFEST_SEAL_NAME: {"size": 2, "sha256": _sha256(b"{}")},
            },
        }
        with zipfile.ZipFile(zp, "w") as zf:
            zf.writestr("../secret.txt", content)
            zf.writestr(MANIFEST_SEAL_NAME, b"{}")
            zf.writestr(MANIFEST_NAME, _manifest_json_bytes(manifest))
            zf.writestr(MANIFEST_TEXT_NAME, b"text\n")
        rc = handle(_make_args(zip=str(zp), verify_json=True))
        assert rc == 1
        data = json.loads(capsys.readouterr().out)
        assert any("traversal" in e for e in data["errors"])


class TestCLIFlags:
    def test_zip_flag_supported(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        zp = tmp_path / "good.zip"
        _build_valid_zip(zp)
        rc = handle(_make_args(zip="", zip_opt=str(zp), verify_json=True))
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["ok"] is True

    def test_missing_zip_argument(self) -> None:
        rc = handle(_make_args(zip="", zip_opt=""))
        assert rc == 2


class TestRegister:
    def test_bundle_verify_subcommand(self) -> None:
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        register(sub)
        args = parser.parse_args(["bundle", "verify", "test.zip"])
        assert args.bundle_command == "verify"
        assert args.zip == "test.zip"

    def test_bundle_verify_subcommand_zip_flag(self) -> None:
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        register(sub)
        args = parser.parse_args(["bundle", "verify", "--zip", "test.zip", "--no-strict"])
        assert args.bundle_command == "verify"
        assert args.zip_opt == "test.zip"
        assert args.verify_strict is False
