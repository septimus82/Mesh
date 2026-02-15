from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest

from mesh_cli.release import handle
from mesh_cli.release_notes import ReleaseNotes, ReleaseSection


def _make_args(**overrides: object) -> argparse.Namespace:
    defaults: dict[str, Any] = {
        "command": "release",
        "release_command": "notes",
        "since": None,
        "until": None,
        "out": None,
        "notes_json": False,
        "deterministic": False,
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
            ReleaseSection(title="Features", items=["add deterministic release notes"]),
            ReleaseSection(title="Fixes", items=["repair bundle manifest coverage"]),
        ],
    )


def test_release_notes_command_prints_text(monkeypatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr("mesh_cli.release.generate_release_notes", lambda **_kwargs: _sample_notes())
    rc = handle(_make_args(notes_json=False, out=None, deterministic=True))
    assert rc == 0
    out = capsys.readouterr().out
    assert "Mesh Release Notes" in out
    assert "Version: 0.4.0" in out
    assert "Features:" in out


def test_release_notes_command_prints_json(monkeypatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr("mesh_cli.release.generate_release_notes", lambda **_kwargs: _sample_notes())
    rc = handle(_make_args(notes_json=True, out=None, deterministic=True))
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["generated_mode"] == "deterministic"
    assert data["version"] == "0.4.0"
    assert data["sections"][0]["title"] == "Features"


def test_release_notes_command_out_dir_writes_text_file(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("mesh_cli.release.generate_release_notes", lambda **_kwargs: _sample_notes())
    out_dir = tmp_path / "notes"
    rc = handle(_make_args(notes_json=False, out=str(out_dir), deterministic=True))
    assert rc == 0
    out_path = out_dir / "release_notes.txt"
    assert out_path.exists()
    assert "Mesh Release Notes" in out_path.read_text(encoding="utf-8")


def test_release_notes_command_out_dir_writes_json_file(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("mesh_cli.release.generate_release_notes", lambda **_kwargs: _sample_notes())
    out_dir = tmp_path / "notes_json"
    rc = handle(_make_args(notes_json=True, out=str(out_dir), deterministic=True))
    assert rc == 0
    out_path = out_dir / "release_notes.json"
    assert out_path.exists()
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["version"] == "0.4.0"


def test_release_notes_command_passes_deterministic_flag(monkeypatch) -> None:
    seen: dict[str, object] = {}

    def _fake_generate_release_notes(*, deterministic: bool, since: str | None, until: str | None) -> ReleaseNotes:
        seen["deterministic"] = deterministic
        seen["since"] = since
        seen["until"] = until
        return _sample_notes()

    monkeypatch.setattr("mesh_cli.release.generate_release_notes", _fake_generate_release_notes)
    rc = handle(_make_args(deterministic=True, since="v0.3.9", until="HEAD", out=None))
    assert rc == 0
    assert seen == {"deterministic": True, "since": "v0.3.9", "until": "HEAD"}

