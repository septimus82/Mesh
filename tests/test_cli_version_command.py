"""Tests for ``mesh_cli version`` command."""
from __future__ import annotations

import argparse
import json

import pytest

from engine import __version__ as ENGINE_INIT_VERSION
from mesh_cli.version import handle, register


def _make_args(**overrides: object) -> argparse.Namespace:
    defaults = {
        "command": "version",
        "version_json": False,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


class TestVersionText:
    """``mesh_cli version`` prints human-readable provenance."""

    def test_prints_tool_name(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = handle(_make_args())
        assert rc == 0
        out = capsys.readouterr().out
        assert "Mesh Engine" in out

    def test_prints_python(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = handle(_make_args())
        assert rc == 0
        assert "Python:" in capsys.readouterr().out

    def test_prints_platform(self, capsys: pytest.CaptureFixture[str]) -> None:
        handle(_make_args())
        assert "Platform:" in capsys.readouterr().out


class TestVersionJSON:
    """``mesh_cli version --json`` prints provenance as JSON."""

    def test_valid_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = handle(_make_args(version_json=True))
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert isinstance(data, dict)
        assert "tool_name" in data
        assert "tool_version" in data

    def test_json_has_python_version(self, capsys: pytest.CaptureFixture[str]) -> None:
        handle(_make_args(version_json=True))
        data = json.loads(capsys.readouterr().out)
        assert "python_version" in data

    def test_json_tool_version_matches_engine_init(self, capsys: pytest.CaptureFixture[str]) -> None:
        handle(_make_args(version_json=True))
        data = json.loads(capsys.readouterr().out)
        assert data["tool_version"] == ENGINE_INIT_VERSION


class TestVersionRegister:
    """register() wires up the subparser."""

    def test_creates_version_subcommand(self) -> None:
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        register(sub)
        args = parser.parse_args(["version"])
        assert args.command == "version"

    def test_json_flag(self) -> None:
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        register(sub)
        args = parser.parse_args(["version", "--json"])
        assert args.version_json is True
