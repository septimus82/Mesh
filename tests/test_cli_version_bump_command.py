from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest

from mesh_cli.version import handle
from mesh_cli.version_bump import apply_version_update


def _make_args(**overrides: object) -> argparse.Namespace:
    defaults: dict[str, Any] = {
        "command": "version",
        "version_command": "bump",
        "kind": "patch",
        "dry_run": False,
        "bump_json": False,
        "quiet": True,
        "version_json": False,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _write_version_file(path: Path, version: str) -> None:
    path.write_text(f'ENGINE_VERSION = "{version}"\n', encoding="utf-8")


def test_version_bump_patch_minor_major(tmp_path: Path, monkeypatch) -> None:
    version_file = tmp_path / "version.py"
    _write_version_file(version_file, "1.2.3")
    monkeypatch.setattr("mesh_cli.version_bump.get_version_file_path", lambda: version_file)

    rc = handle(_make_args(kind="patch"))
    assert rc == 0
    assert 'ENGINE_VERSION = "1.2.4"' in version_file.read_text(encoding="utf-8")

    rc = handle(_make_args(kind="minor"))
    assert rc == 0
    assert 'ENGINE_VERSION = "1.3.0"' in version_file.read_text(encoding="utf-8")

    rc = handle(_make_args(kind="major"))
    assert rc == 0
    assert 'ENGINE_VERSION = "2.0.0"' in version_file.read_text(encoding="utf-8")


def test_version_bump_dry_run_does_not_modify_file(tmp_path: Path, monkeypatch, capsys: pytest.CaptureFixture[str]) -> None:
    version_file = tmp_path / "version.py"
    _write_version_file(version_file, "0.9.9")
    monkeypatch.setattr("mesh_cli.version_bump.get_version_file_path", lambda: version_file)

    before = version_file.read_text(encoding="utf-8")
    rc = handle(_make_args(kind="patch", dry_run=True, bump_json=True))
    assert rc == 0
    after = version_file.read_text(encoding="utf-8")
    assert after == before
    payload = json.loads(capsys.readouterr().out)
    assert payload["old"] == "0.9.9"
    assert payload["new"] == "0.9.10"


def test_version_bump_refuses_invalid_current_format(tmp_path: Path, monkeypatch) -> None:
    version_file = tmp_path / "version.py"
    _write_version_file(version_file, "dev-build")
    monkeypatch.setattr("mesh_cli.version_bump.get_version_file_path", lambda: version_file)

    rc = handle(_make_args(kind="patch"))
    assert rc == 1


def test_apply_version_update_refuses_zero_or_multiple_literal_matches(tmp_path: Path) -> None:
    zero_file = tmp_path / "zero.py"
    zero_file.write_text('ENGINE_VERSION = "1.2.3"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="not found"):
        apply_version_update(zero_file, "9.9.9", "10.0.0")

    many_file = tmp_path / "many.py"
    many_file.write_text(
        'ENGINE_VERSION = "1.2.3"\nOTHER_VERSION = "1.2.3"\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="appears 2 times"):
        apply_version_update(many_file, "1.2.3", "1.2.4")

