from __future__ import annotations

import argparse
import subprocess
from typing import Any

import pytest

from mesh_cli.release import handle
from mesh_cli.release_notes import ReleaseNotes, ReleaseSection


def _make_args(**overrides: object) -> argparse.Namespace:
    defaults: dict[str, Any] = {
        "command": "release",
        "release_command": "tag",
        "name": None,
        "auto": False,
        "message": None,
        "dry_run": False,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _cp(args: list[str], *, code: int = 0, out: str = "", err: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=args, returncode=code, stdout=out, stderr=err)


def _sample_notes() -> ReleaseNotes:
    return ReleaseNotes(
        version="0.4.0",
        generated_mode="deterministic",
        sections=[ReleaseSection(title="Other", items=["noop"])],
    )


def test_release_tag_dry_run_uses_auto_version(monkeypatch, capsys: pytest.CaptureFixture[str]) -> None:
    calls: list[list[str]] = []

    def _fake_git_run(args: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        if args == ["--version"]:
            return _cp(args, out="git version 2.45.0\n")
        if args[:3] == ["rev-parse", "-q", "--verify"]:
            return _cp(args, code=1)
        return _cp(args, code=1)

    monkeypatch.setattr("mesh_cli.release._git_run", _fake_git_run)
    monkeypatch.setattr("mesh_cli.release.get_tool_version", lambda: "0.4.0")
    monkeypatch.setattr("mesh_cli.release.generate_release_notes", lambda **_kwargs: _sample_notes())
    monkeypatch.setattr("mesh_cli.release.format_release_notes_text", lambda _notes: "Mesh Release Notes\n")

    rc = handle(_make_args(auto=True, dry_run=True))
    assert rc == 0
    out = capsys.readouterr().out
    assert "Dry-run:" in out
    assert "v0.4.0" in out
    assert calls[0] == ["--version"]
    assert calls[1][:3] == ["rev-parse", "-q", "--verify"]


def test_release_tag_fails_when_tag_exists(monkeypatch, capsys: pytest.CaptureFixture[str]) -> None:
    def _fake_git_run(args: list[str]) -> subprocess.CompletedProcess[str]:
        if args == ["--version"]:
            return _cp(args, out="git version 2.45.0\n")
        if args[:3] == ["rev-parse", "-q", "--verify"]:
            return _cp(args, code=0, out="taghash\n")
        return _cp(args, code=1)

    monkeypatch.setattr("mesh_cli.release._git_run", _fake_git_run)
    rc = handle(_make_args(name="v0.4.0"))
    assert rc == 1
    assert "tag already exists" in capsys.readouterr().out


def test_release_tag_fails_when_git_unavailable(monkeypatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr("mesh_cli.release._git_run", lambda _args: None)
    rc = handle(_make_args(name="v0.4.0"))
    assert rc == 2
    assert "git is unavailable" in capsys.readouterr().out


def test_release_tag_creates_annotated_tag(monkeypatch, capsys: pytest.CaptureFixture[str]) -> None:
    calls: list[list[str]] = []

    def _fake_git_run(args: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        if args == ["--version"]:
            return _cp(args, out="git version 2.45.0\n")
        if args[:3] == ["rev-parse", "-q", "--verify"]:
            return _cp(args, code=1)
        if args[:3] == ["tag", "-a", "v0.4.0"]:
            return _cp(args, code=0)
        return _cp(args, code=1)

    monkeypatch.setattr("mesh_cli.release._git_run", _fake_git_run)
    rc = handle(_make_args(name="v0.4.0", message="release tag message"))
    assert rc == 0
    assert any(call[:3] == ["tag", "-a", "v0.4.0"] for call in calls)
    assert "Created local tag: v0.4.0" in capsys.readouterr().out

