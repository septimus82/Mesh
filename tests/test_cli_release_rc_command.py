from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest

from mesh_cli.release import handle
from mesh_cli.release_notes import ReleaseNotes, ReleaseSection, format_release_notes_text, release_notes_to_dict


def _make_args(out_path: Path, **overrides: object) -> argparse.Namespace:
    defaults: dict[str, Any] = {
        "command": "release",
        "release_command": "rc",
        "out": str(out_path),
        "seed": 123,
        "rc_version": None,
        "rc_bump": None,
        "since": None,
        "no_write_version": False,
        "no_rollback": False,
        "quiet": True,
        "rc_json": False,
        "dry_run": False,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _sample_notes() -> ReleaseNotes:
    return ReleaseNotes(
        version="0.4.0",
        generated_mode="deterministic",
        git_commit="abc123",
        git_dirty=False,
        range_from="v0.3.9",
        range_to="HEAD",
        sections=[
            ReleaseSection(title="Features", items=["add RC pipeline"]),
            ReleaseSection(title="Tooling", items=["wire deterministic release flow"]),
        ],
    )


def _write_minimal_rc_bundle(zip_path: Path, notes: ReleaseNotes) -> None:
    from engine.persistence_io import write_json_atomic, write_text_atomic
    from mesh_cli.release_bundle import FileEntry, ReleaseBundlePlan, build_release_bundle_zip

    work_dir = zip_path.parent / f"_stub_work_{zip_path.stem}"
    if work_dir.exists():
        import shutil

        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "payload.txt").write_text("payload", encoding="utf-8")
    write_notes_json = release_notes_to_dict(notes)
    write_json_atomic(work_dir / "release_notes.json", write_notes_json, indent=2, sort_keys=True, trailing_newline=True)
    write_text_atomic(work_dir / "release_notes.txt", format_release_notes_text(notes), encoding="utf-8")

    payload = work_dir / "payload.txt"
    plan = ReleaseBundlePlan(
        files=[FileEntry(archive_path="payload.txt", disk_path=payload)],
        seed=123,
        campaign="mini_campaign_01",
        work_dir=work_dir,
    )
    build_release_bundle_zip(plan, zip_path, timestamp="1980-01-01T00:00:00Z")


def _rc_report_json_path(zip_path: Path) -> Path:
    return zip_path.with_name(f"{zip_path.name}.rc_report.json")


def test_release_rc_orchestration_order_and_report_fields(tmp_path: Path, monkeypatch) -> None:
    out_zip = tmp_path / "rc.zip"
    calls: list[str] = []
    notes = _sample_notes()

    def _fake_generate(*, deterministic: bool, since: str | None, until: str | None) -> ReleaseNotes:
        calls.append("notes")
        assert deterministic is True
        assert until == "HEAD"
        return notes

    def _fake_create_tag(*, tag_name: str, message: str) -> tuple[str, str | None]:
        calls.append("tag")
        assert tag_name == "v9.9.9"
        assert "Mesh Release Notes" in message
        return "created", None

    def _fake_bundle_handle(args: argparse.Namespace) -> int:
        calls.append("bundle")
        _write_minimal_rc_bundle(Path(args.out), notes)
        return 0

    def _fake_verify(_zip_path: str, *, options) -> dict[str, Any]:
        calls.append("verify")
        return {
            "ok": True,
            "counts": {"verified_files": 5, "verifiable_files": 5},
            "sealed_manifest_verified": True,
        }

    monkeypatch.setattr("mesh_cli.release.generate_release_notes", _fake_generate)
    monkeypatch.setattr("mesh_cli.release._git_available", lambda: True)
    monkeypatch.setattr("mesh_cli.release._create_local_tag", _fake_create_tag)
    monkeypatch.setattr("mesh_cli.release_bundle.handle", _fake_bundle_handle)
    monkeypatch.setattr("mesh_cli.bundle_verify.verify_zip", _fake_verify)

    rc = handle(_make_args(out_zip, rc_version="9.9.9"))
    assert rc == 0
    assert calls == ["notes", "tag", "bundle", "verify"]

    report = json.loads(_rc_report_json_path(out_zip).read_text(encoding="utf-8"))
    assert report["ok"] is True
    assert report["version"] == "9.9.9"
    assert [step["name"] for step in report["steps"]] == [
        "determine-version",
        "generate-release-notes",
        "local-tag",
        "build-release-bundle",
        "bundle-verify-strict",
    ]


def test_release_rc_git_missing_skips_tag_and_succeeds(tmp_path: Path, monkeypatch) -> None:
    out_zip = tmp_path / "rc_gitless.zip"
    notes = _sample_notes()
    monkeypatch.setattr("mesh_cli.release.generate_release_notes", lambda **_kwargs: notes)
    monkeypatch.setattr("mesh_cli.release._git_available", lambda: False)
    monkeypatch.setattr("mesh_cli.release._create_local_tag", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("tag should not run")))
    monkeypatch.setattr("mesh_cli.release_bundle.handle", lambda args: (_write_minimal_rc_bundle(Path(args.out), notes), 0)[1])

    rc = handle(_make_args(out_zip))
    assert rc == 0
    report = json.loads(_rc_report_json_path(out_zip).read_text(encoding="utf-8"))
    assert report["tag"]["status"] == "skipped"
    assert report["tag"]["reason"] == "git unavailable"
    tag_step = next(step for step in report["steps"] if step["name"] == "local-tag")
    assert tag_step["skipped"] is True


def test_release_rc_dry_run_does_not_build_or_tag(tmp_path: Path, monkeypatch, capsys: pytest.CaptureFixture[str]) -> None:
    out_zip = tmp_path / "rc_dry.zip"
    notes = _sample_notes()
    monkeypatch.setattr("mesh_cli.release.generate_release_notes", lambda **_kwargs: notes)
    monkeypatch.setattr("mesh_cli.release._create_local_tag", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("tag should not run")))
    monkeypatch.setattr(
        "mesh_cli.release_bundle.handle",
        lambda _args: (_ for _ in ()).throw(AssertionError("bundle should not run")),
    )

    rc = handle(_make_args(out_zip, dry_run=True, quiet=False))
    assert rc == 0
    assert not out_zip.exists()
    out = capsys.readouterr().out
    assert "Would build release bundle" in out
    report = json.loads(_rc_report_json_path(out_zip).read_text(encoding="utf-8"))
    assert report["ok"] is True
    assert next(step for step in report["steps"] if step["name"] == "build-release-bundle")["skipped"] is True


def test_release_rc_success_path_writes_verified_bundle_and_report(tmp_path: Path, monkeypatch) -> None:
    out_zip = tmp_path / "rc_success.zip"
    notes = _sample_notes()
    monkeypatch.setattr("mesh_cli.release.generate_release_notes", lambda **_kwargs: notes)
    monkeypatch.setattr("mesh_cli.release._git_available", lambda: False)
    monkeypatch.setattr("mesh_cli.release_bundle.handle", lambda args: (_write_minimal_rc_bundle(Path(args.out), notes), 0)[1])

    rc = handle(_make_args(out_zip))
    assert rc == 0
    assert out_zip.exists()
    report_path = _rc_report_json_path(out_zip)
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["ok"] is True
    assert report["bundle"]["sealed_manifest_verified"] is True
    assert int(report["bundle"]["verified_count"]) == int(report["bundle"]["verifiable_files"])


def test_release_rc_verify_failure_deletes_zip_and_reports_error(tmp_path: Path, monkeypatch) -> None:
    out_zip = tmp_path / "rc_fail_verify.zip"
    notes = _sample_notes()
    monkeypatch.setattr("mesh_cli.release.generate_release_notes", lambda **_kwargs: notes)
    monkeypatch.setattr("mesh_cli.release._git_available", lambda: False)
    monkeypatch.setattr("mesh_cli.release_bundle.handle", lambda args: (_write_minimal_rc_bundle(Path(args.out), notes), 0)[1])
    monkeypatch.setattr(
        "mesh_cli.bundle_verify.verify_zip",
        lambda *_args, **_kwargs: {"ok": False, "errors": ["forced mismatch"], "counts": {}},
    )

    rc = handle(_make_args(out_zip))
    assert rc == 1
    assert not out_zip.exists()
    report = json.loads(_rc_report_json_path(out_zip).read_text(encoding="utf-8"))
    assert report["ok"] is False
    verify_step = next(step for step in report["steps"] if step["name"] == "bundle-verify-strict")
    assert verify_step["ok"] is False


def test_release_rc_bump_patch_updates_version_and_report(tmp_path: Path, monkeypatch) -> None:
    out_zip = tmp_path / "rc_bump.zip"
    notes = _sample_notes()
    version_file = tmp_path / "version.py"
    version_file.write_text('ENGINE_VERSION = "1.2.3"\n', encoding="utf-8")

    monkeypatch.setattr("mesh_cli.version_info.get_version_file_path", lambda: version_file)
    monkeypatch.setattr("mesh_cli.version_bump.get_version_file_path", lambda: version_file)
    monkeypatch.setattr("mesh_cli.release.generate_release_notes", lambda **_kwargs: notes)
    monkeypatch.setattr("mesh_cli.release._git_available", lambda: False)
    monkeypatch.setattr("mesh_cli.release_bundle.handle", lambda args: (_write_minimal_rc_bundle(Path(args.out), notes), 0)[1])

    rc = handle(_make_args(out_zip, rc_bump="patch"))
    assert rc == 0
    assert 'ENGINE_VERSION = "1.2.4"' in version_file.read_text(encoding="utf-8")
    report = json.loads(_rc_report_json_path(out_zip).read_text(encoding="utf-8"))
    assert report["version"] == "1.2.4"
    assert report["version_bump"]["wrote"] is True
    bump_step = next(step for step in report["steps"] if step["name"] == "bump-version")
    assert bump_step["ok"] is True


def test_release_rc_bump_failure_rolls_back_version_file(tmp_path: Path, monkeypatch) -> None:
    out_zip = tmp_path / "rc_bump_fail.zip"
    notes = _sample_notes()
    version_file = tmp_path / "version.py"
    original = 'ENGINE_VERSION = "2.3.4"\n'
    version_file.write_text(original, encoding="utf-8")

    monkeypatch.setattr("mesh_cli.version_info.get_version_file_path", lambda: version_file)
    monkeypatch.setattr("mesh_cli.version_bump.get_version_file_path", lambda: version_file)
    monkeypatch.setattr("mesh_cli.release.generate_release_notes", lambda **_kwargs: notes)
    monkeypatch.setattr("mesh_cli.release._git_available", lambda: False)
    monkeypatch.setattr("mesh_cli.release_bundle.handle", lambda args: (_write_minimal_rc_bundle(Path(args.out), notes), 0)[1])
    monkeypatch.setattr(
        "mesh_cli.bundle_verify.verify_zip",
        lambda *_args, **_kwargs: {"ok": False, "errors": ["forced mismatch"], "counts": {}},
    )

    rc = handle(_make_args(out_zip, rc_bump="patch"))
    assert rc == 1
    assert version_file.read_text(encoding="utf-8") == original
    report = json.loads(_rc_report_json_path(out_zip).read_text(encoding="utf-8"))
    assert report["version_bump"]["rolled_back"] is True


def test_release_rc_dry_run_with_bump_does_not_modify_version_file(tmp_path: Path, monkeypatch) -> None:
    out_zip = tmp_path / "rc_bump_dry.zip"
    notes = _sample_notes()
    version_file = tmp_path / "version.py"
    original = 'ENGINE_VERSION = "3.0.0"\n'
    version_file.write_text(original, encoding="utf-8")

    monkeypatch.setattr("mesh_cli.version_info.get_version_file_path", lambda: version_file)
    monkeypatch.setattr("mesh_cli.version_bump.get_version_file_path", lambda: version_file)
    monkeypatch.setattr("mesh_cli.release.generate_release_notes", lambda **_kwargs: notes)
    monkeypatch.setattr(
        "mesh_cli.release_bundle.handle",
        lambda _args: (_ for _ in ()).throw(AssertionError("bundle should not run in dry-run")),
    )

    rc = handle(_make_args(out_zip, rc_bump="patch", dry_run=True))
    assert rc == 0
    assert version_file.read_text(encoding="utf-8") == original
    report = json.loads(_rc_report_json_path(out_zip).read_text(encoding="utf-8"))
    assert report["version"] == "3.0.1"
    assert report["version_bump"]["wrote"] is False
