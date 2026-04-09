from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest


pytestmark = [pytest.mark.fast]


def test_release_rc_reporting_helpers_remain_patchable_from_release_module() -> None:
    release_mod = importlib.import_module("mesh_cli.release")
    reporting_mod = importlib.import_module("mesh_cli.release_rc_reporting")
    for name in (
        "_build_rc_report",
        "_set_rc_version_bump",
        "_set_rc_version_bump_rolled_back",
        "_update_rc_bundle_report",
    ):
        assert getattr(release_mod, name, None) is getattr(
            reporting_mod, name, None
        ), f"release rc reporting helper drifted: {name}"


def test_release_rc_reporting_module_surface_stays_focused() -> None:
    source_path = Path("mesh_cli/release_rc_reporting.py")
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))

    top_level_defs = [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    ]
    assert top_level_defs == [
        "_build_rc_report",
        "_set_rc_version_bump",
        "_set_rc_version_bump_rolled_back",
        "_update_rc_bundle_report",
    ]
