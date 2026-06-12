from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]


def test_release_rc_helpers_remain_patchable_from_release_module() -> None:
    release_mod = importlib.import_module("mesh_cli.release")
    helpers_mod = importlib.import_module("mesh_cli.release_rc_helpers")
    for name in (
        "_git_run",
        "_git_available",
        "_git_tag_exists",
        "_default_tag_message",
        "_create_local_tag",
    ):
        assert getattr(release_mod, name, None) is getattr(
            helpers_mod, name, None
        ), f"release rc helper drifted: {name}"


def test_release_rc_helpers_module_surface_stays_focused() -> None:
    source_path = Path("mesh_cli/release_rc_helpers.py")
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))

    top_level_defs = [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    ]
    assert top_level_defs == [
        "_git_run",
        "_git_available",
        "_git_tag_exists",
        "_default_tag_message",
        "_create_local_tag",
    ]
