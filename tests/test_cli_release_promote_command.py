from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from typing import Any

from mesh_cli.bundle_verify import DEFAULT_EXCLUDE_RULES, VerifyOptions, verify_zip
from mesh_cli.release import handle


def _make_args(rc_zip: Path, out_zip: Path, **overrides: object) -> argparse.Namespace:
    defaults: dict[str, Any] = {
        "command": "release",
        "release_command": "promote",
        "rc": str(rc_zip),
        "out": str(out_zip),
        "promote_version": None,
        "tag": False,
        "notes_since": None,
        "quiet": True,
        "promote_json": False,
        "dry_run": False,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _promote_report_json_path(out_zip: Path) -> Path:
    return out_zip.with_name(f"{out_zip.name}.promote_report.json")


def _build_minimal_rc_zip(zip_path: Path) -> None:
    from mesh_cli.release_bundle import FileEntry, ReleaseBundlePlan, build_release_bundle_zip

    work_dir = zip_path.parent / f"_rc_work_{zip_path.stem}"
    if work_dir.exists():
        import shutil

        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "payload.txt").write_text("payload", encoding="utf-8")

    plan = ReleaseBundlePlan(
        files=[FileEntry(archive_path="payload.txt", disk_path=work_dir / "payload.txt")],
        seed=123,
        campaign="mini_campaign_01",
        work_dir=work_dir,
    )
    build_release_bundle_zip(plan, zip_path, timestamp="1980-01-01T00:00:00Z")


def test_release_promote_happy_path_embeds_reports_and_verifies(tmp_path: Path, monkeypatch) -> None:
    rc_zip = tmp_path / "rc_bundle.zip"
    out_zip = tmp_path / "release_final.zip"
    _build_minimal_rc_zip(rc_zip)

    monkeypatch.setattr("mesh_cli.release._git_available", lambda: False)

    rc = handle(_make_args(rc_zip, out_zip))
    assert rc == 0
    assert out_zip.exists()
    assert _promote_report_json_path(out_zip).exists()

    with zipfile.ZipFile(out_zip, "r") as zf:
        names = set(zf.namelist())
    assert "promote/promote_report.json" in names
    assert "promote/promote_report.txt" in names

    verify_report = verify_zip(
        str(out_zip),
        options=VerifyOptions(strict=True, exclude=DEFAULT_EXCLUDE_RULES),
    )
    assert verify_report["ok"] is True

    report = json.loads(_promote_report_json_path(out_zip).read_text(encoding="utf-8"))
    assert report["ok"] is True
    assert report["rc_verify"]["ok"] is True
    assert report["final_verify"]["ok"] is True
    assert [step["name"] for step in report["steps"]] == [
        "verify-rc-strict",
        "determine-version",
        "local-tag",
        "build-final-zip",
        "verify-final-strict",
    ]


def test_release_promote_fails_fast_on_corrupt_rc_and_does_not_create_output(
    tmp_path: Path, monkeypatch
) -> None:
    rc_zip = tmp_path / "rc_corrupt.zip"
    out_zip = tmp_path / "release_final.zip"
    _build_minimal_rc_zip(rc_zip)
    monkeypatch.setattr("mesh_cli.release._git_available", lambda: False)

    tampered_zip = tmp_path / "rc_corrupt_tmp.zip"
    with zipfile.ZipFile(rc_zip, "r") as src, zipfile.ZipFile(tampered_zip, "w", compression=zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            data = b"" if info.is_dir() else src.read(info.filename)
            if info.filename == "payload.txt":
                data = b"tampered"
            out_info = zipfile.ZipInfo(filename=info.filename, date_time=info.date_time)
            out_info.compress_type = zipfile.ZIP_DEFLATED
            out_info.external_attr = info.external_attr
            dst.writestr(out_info, data)
    tampered_zip.replace(rc_zip)

    rc = handle(_make_args(rc_zip, out_zip))
    assert rc == 1
    assert not out_zip.exists()
    report = json.loads(_promote_report_json_path(out_zip).read_text(encoding="utf-8"))
    assert report["ok"] is False
    first_step = report["steps"][0]
    assert first_step["name"] == "verify-rc-strict"
    assert first_step["ok"] is False


def test_release_promote_deterministic_for_same_inputs(tmp_path: Path, monkeypatch) -> None:
    rc_zip = tmp_path / "rc_deterministic.zip"
    out_zip = tmp_path / "release_final.zip"
    _build_minimal_rc_zip(rc_zip)
    monkeypatch.setattr("mesh_cli.release._git_available", lambda: False)

    rc1 = handle(_make_args(rc_zip, out_zip, promote_version="9.1.0"))
    assert rc1 == 0
    first = out_zip.read_bytes()

    rc2 = handle(_make_args(rc_zip, out_zip, promote_version="9.1.0"))
    assert rc2 == 0
    second = out_zip.read_bytes()

    assert first == second


def test_release_promote_git_missing_with_tag_skips_and_succeeds(tmp_path: Path, monkeypatch) -> None:
    rc_zip = tmp_path / "rc_gitless.zip"
    out_zip = tmp_path / "release_final.zip"
    _build_minimal_rc_zip(rc_zip)

    monkeypatch.setattr("mesh_cli.release._git_available", lambda: False)
    monkeypatch.setattr(
        "mesh_cli.release._create_local_tag",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("tag should not run")),
    )

    rc = handle(_make_args(rc_zip, out_zip, tag=True))
    assert rc == 0
    report = json.loads(_promote_report_json_path(out_zip).read_text(encoding="utf-8"))
    assert report["tag"]["status"] == "skipped"
    assert report["tag"]["reason"] == "git unavailable"
    tag_step = next(step for step in report["steps"] if step["name"] == "local-tag")
    assert tag_step["skipped"] is True


def test_release_promote_dry_run_writes_report_only(tmp_path: Path, monkeypatch) -> None:
    rc_zip = tmp_path / "rc_dry.zip"
    out_zip = tmp_path / "release_final.zip"
    _build_minimal_rc_zip(rc_zip)
    monkeypatch.setattr("mesh_cli.release._git_available", lambda: False)

    rc = handle(_make_args(rc_zip, out_zip, dry_run=True, tag=True))
    assert rc == 0
    assert not out_zip.exists()
    report = json.loads(_promote_report_json_path(out_zip).read_text(encoding="utf-8"))
    assert report["ok"] is True
    build_step = next(step for step in report["steps"] if step["name"] == "build-final-zip")
    verify_step = next(step for step in report["steps"] if step["name"] == "verify-final-strict")
    assert build_step["skipped"] is True
    assert verify_step["skipped"] is True
