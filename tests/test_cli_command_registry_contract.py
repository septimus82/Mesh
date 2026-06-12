from __future__ import annotations

from pathlib import Path

import pytest

import mesh_cli
from mesh_cli.main import create_parser

pytestmark = [pytest.mark.fast]


def test_cli_parser_registers_expected_core_subcommands() -> None:
    parser = create_parser()
    subparsers_action = next(
        action for action in parser._actions if action.__class__.__name__ == "_SubParsersAction"  # noqa: SLF001
    )
    choices = set(subparsers_action.choices.keys())
    for command in (
        "verify-all",
        "verify-local",
        "verify-demo",
        "verify-strict",
        "scene",
        "world",
        "pipeline",
        "plan",
        "preset",
        "run-preset",
    ):
        assert command in choices, f"missing CLI subcommand '{command}'"


def test_mesh_cli_main_uses_canonical_dispatch_module() -> None:
    source = Path("mesh_cli/main.py").read_text(encoding="utf-8")
    assert "from .legacy.dispatch import create_parser" in source
    assert "from .legacy.dispatch import main" in source
    assert "from .legacy import create_parser" not in source
    assert "from .legacy import main" not in source


def test_mesh_cli_package_surface_still_exports_main_and_parser() -> None:
    assert callable(getattr(mesh_cli, "create_parser", None))
    assert callable(getattr(mesh_cli, "main", None))
