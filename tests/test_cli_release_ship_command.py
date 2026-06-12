from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from mesh_cli.release import handle


def _make_args(out_dir: Path, **overrides: object) -> argparse.Namespace:
    defaults: dict[str, Any] = {
        "command": "release",
        "release_command": "ship",
        "out_dir": str(out_dir),
        "seed": 123,
        "ship_bump": None,
        "tag": False,
        "since": None,
        "quiet": True,
        "ship_json": False,
        "dry_run": False,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _ship_report_json(out_dir: Path) -> Path:
    return out_dir / "ship_report.json"


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def test_release_ship_orchestration_order(tmp_path: Path, monkeypatch) -> None:
    out_dir = tmp_path / "ship"
    calls: list[str] = []

    def _fake_rc(args: argparse.Namespace) -> int:
        calls.append("rc")
        Path(args.out).write_bytes(b"RC-ZIP")
        rc_json = Path(args.out).with_name(f"{Path(args.out).name}.rc_report.json")
        _write_json(rc_json, {"ok": True, "version": "1.2.3", "tag": {"status": "skipped"}})
        _write_json(rc_json.with_suffix(".txt"), {"ok": True})
        return 0

    def _fake_promote(args: argparse.Namespace) -> int:
        calls.append("promote")
        Path(args.out).write_bytes(b"FINAL-ZIP")
        promote_json = Path(args.out).with_name(f"{Path(args.out).name}.promote_report.json")
        _write_json(
            promote_json,
            {"ok": True, "version": "1.2.3", "tag": {"status": "skipped", "reason": "disabled"}},
        )
        _write_json(promote_json.with_suffix(".txt"), {"ok": True})
        return 0

    def _fake_verify(zip_path: str, *, options) -> dict[str, Any]:
        if str(zip_path).endswith("rc_bundle.zip"):
            calls.append("verify-rc")
        else:
            calls.append("verify-final")
        return {
            "ok": True,
            "counts": {"verified_files": 10, "verifiable_files": 10, "manifest_files": 8},
            "sealed_manifest_verified": True,
        }

    monkeypatch.setattr("mesh_cli.release._handle_rc", _fake_rc)
    monkeypatch.setattr("mesh_cli.release._handle_promote", _fake_promote)
    monkeypatch.setattr("mesh_cli.bundle_verify.verify_zip", _fake_verify)

    rc = handle(_make_args(out_dir))
    assert rc == 0
    assert calls == ["rc", "promote", "verify-rc", "verify-final"]

    report = json.loads(_ship_report_json(out_dir).read_text(encoding="utf-8"))
    assert report["ok"] is True
    assert [step["name"] for step in report["steps"]] == [
        "content-audit",
        "prepare-version",
        "build-rc",
        "promote-final",
        "verify-artifacts-strict",
    ]


def test_release_ship_failure_propagates_and_cleans_final_zip(tmp_path: Path, monkeypatch) -> None:
    out_dir = tmp_path / "ship"
    final_zip = out_dir / "release_final.zip"

    def _fake_rc(args: argparse.Namespace) -> int:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_bytes(b"RC-ZIP")
        _write_json(Path(args.out).with_name(f"{Path(args.out).name}.rc_report.json"), {"ok": True})
        return 0

    def _fake_promote(args: argparse.Namespace) -> int:
        Path(args.out).write_bytes(b"PARTIAL-FINAL")
        _write_json(Path(args.out).with_name(f"{Path(args.out).name}.promote_report.json"), {"ok": False})
        return 1

    monkeypatch.setattr("mesh_cli.release._handle_rc", _fake_rc)
    monkeypatch.setattr("mesh_cli.release._handle_promote", _fake_promote)
    monkeypatch.setattr(
        "mesh_cli.bundle_verify.verify_zip",
        lambda *_args, **_kwargs: {
            "ok": True,
            "counts": {"verified_files": 1, "verifiable_files": 1, "manifest_files": 1},
            "sealed_manifest_verified": True,
        },
    )

    rc = handle(_make_args(out_dir))
    assert rc == 1
    assert not final_zip.exists()
    report = json.loads(_ship_report_json(out_dir).read_text(encoding="utf-8"))
    assert report["ok"] is False
    assert report["steps"][-1]["name"] == "promote-final"
    assert report["steps"][-1]["ok"] is False


def test_release_ship_deterministic_outputs_same_seed(tmp_path: Path, monkeypatch) -> None:
    out_dir = tmp_path / "ship"
    rc_zip = out_dir / "rc_bundle.zip"
    final_zip = out_dir / "release_final.zip"

    def _fake_rc(args: argparse.Namespace) -> int:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_bytes(b"RC-DETERMINISTIC")
        _write_json(Path(args.out).with_name(f"{Path(args.out).name}.rc_report.json"), {"ok": True, "version": "1.0.0"})
        return 0

    def _fake_promote(args: argparse.Namespace) -> int:
        Path(args.out).write_bytes(b"FINAL-DETERMINISTIC")
        _write_json(Path(args.out).with_name(f"{Path(args.out).name}.promote_report.json"), {"ok": True, "version": "1.0.0"})
        return 0

    monkeypatch.setattr("mesh_cli.release._handle_rc", _fake_rc)
    monkeypatch.setattr("mesh_cli.release._handle_promote", _fake_promote)
    monkeypatch.setattr(
        "mesh_cli.bundle_verify.verify_zip",
        lambda *_args, **_kwargs: {
            "ok": True,
            "counts": {"verified_files": 2, "verifiable_files": 2, "manifest_files": 2},
            "sealed_manifest_verified": True,
        },
    )

    assert handle(_make_args(out_dir, seed=123)) == 0
    first_rc = rc_zip.read_bytes()
    first_final = final_zip.read_bytes()
    assert handle(_make_args(out_dir, seed=123)) == 0
    second_rc = rc_zip.read_bytes()
    second_final = final_zip.read_bytes()
    assert first_rc == second_rc
    assert first_final == second_final


def test_release_ship_git_missing_tag_is_reported(tmp_path: Path, monkeypatch) -> None:
    out_dir = tmp_path / "ship"

    def _fake_rc(args: argparse.Namespace) -> int:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_bytes(b"RC")
        _write_json(Path(args.out).with_name(f"{Path(args.out).name}.rc_report.json"), {"ok": True})
        return 0

    def _fake_promote(args: argparse.Namespace) -> int:
        Path(args.out).write_bytes(b"FINAL")
        _write_json(
            Path(args.out).with_name(f"{Path(args.out).name}.promote_report.json"),
            {"ok": True, "tag": {"status": "skipped", "reason": "git unavailable"}},
        )
        return 0

    monkeypatch.setattr("mesh_cli.release._handle_rc", _fake_rc)
    monkeypatch.setattr("mesh_cli.release._handle_promote", _fake_promote)
    monkeypatch.setattr(
        "mesh_cli.bundle_verify.verify_zip",
        lambda *_args, **_kwargs: {
            "ok": True,
            "counts": {"verified_files": 2, "verifiable_files": 2, "manifest_files": 2},
            "sealed_manifest_verified": True,
        },
    )

    rc = handle(_make_args(out_dir, tag=True))
    assert rc == 0
    report = json.loads(_ship_report_json(out_dir).read_text(encoding="utf-8"))
    assert report["tag_result"]["status"] == "skipped"
    assert report["tag_result"]["reason"] == "git unavailable"


def test_release_ship_dry_run_creates_no_zips(tmp_path: Path, monkeypatch) -> None:
    out_dir = tmp_path / "ship"

    monkeypatch.setattr(
        "mesh_cli.release._handle_rc",
        lambda _args: (_ for _ in ()).throw(AssertionError("rc should not run")),
    )
    monkeypatch.setattr(
        "mesh_cli.release._handle_promote",
        lambda _args: (_ for _ in ()).throw(AssertionError("promote should not run")),
    )

    rc = handle(_make_args(out_dir, dry_run=True, tag=True, ship_bump="patch"))
    assert rc == 0
    assert not (out_dir / "rc_bundle.zip").exists()
    assert not (out_dir / "release_final.zip").exists()
    report = json.loads(_ship_report_json(out_dir).read_text(encoding="utf-8"))
    assert report["ok"] is True
    content_step = next(step for step in report["steps"] if step["name"] == "content-audit")
    build_step = next(step for step in report["steps"] if step["name"] == "build-rc")
    promote_step = next(step for step in report["steps"] if step["name"] == "promote-final")
    verify_step = next(step for step in report["steps"] if step["name"] == "verify-artifacts-strict")
    assert content_step["skipped"] is True
    assert build_step["skipped"] is True
    assert promote_step["skipped"] is True
    assert verify_step["skipped"] is True
