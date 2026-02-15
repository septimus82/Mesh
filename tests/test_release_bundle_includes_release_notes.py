from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from typing import Any

from mesh_cli.bundle_verify import verify_zip
from mesh_cli.release_bundle import handle
from mesh_cli.release_notes import ReleaseNotes, ReleaseSection


def _fake_step_ok(name: str):
    def _step(work_dir: Path, seed: int, campaign: str) -> tuple[int, dict[str, Any]]:
        out = work_dir / name
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{name}.json").write_text(
            json.dumps({"name": name, "seed": seed, "campaign": campaign}),
            encoding="utf-8",
        )
        return 0, {"dir": f"{name}/"}

    return name, _step


def _make_args(out_path: Path) -> argparse.Namespace:
    return argparse.Namespace(
        command="release",
        release_command="bundle",
        out=str(out_path),
        seed=123,
        campaign="mini_campaign_01",
        report_format="text",
        quiet=True,
    )


def _sample_notes() -> ReleaseNotes:
    return ReleaseNotes(
        version="0.4.0",
        generated_mode="deterministic",
        git_commit="abc123",
        git_dirty=False,
        range_from="v0.3.9",
        range_to="HEAD",
        sections=[
            ReleaseSection(title="Features", items=["add release notes embedding"]),
            ReleaseSection(title="Tooling", items=["wire release notes command"]),
        ],
    )


def test_release_bundle_contains_release_notes_and_manifest_entries(tmp_path: Path, monkeypatch) -> None:
    pipeline = [_fake_step_ok("release"), _fake_step_ok("demo")]
    monkeypatch.setattr("mesh_cli.release_bundle.BUNDLE_PIPELINE", pipeline)
    monkeypatch.setattr("mesh_cli.release_bundle.generate_release_notes", lambda **_kwargs: _sample_notes())

    zip_path = tmp_path / "bundle.zip"
    rc = handle(_make_args(zip_path))
    assert rc == 0

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = set(zf.namelist())
        assert "release_notes.txt" in names
        assert "release_notes.json" in names
        manifest = json.loads(zf.read("package_manifest.json"))
        assert "release_notes.txt" in manifest["files"]
        assert "release_notes.json" in manifest["files"]

    report = verify_zip(str(zip_path))
    assert report["ok"] is True

