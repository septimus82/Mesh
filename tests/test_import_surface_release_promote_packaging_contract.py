from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest


pytestmark = [pytest.mark.fast]


def test_release_promote_packaging_helpers_remain_patchable_from_release_module() -> None:
    release_mod = importlib.import_module("mesh_cli.release")
    packaging_mod = importlib.import_module("mesh_cli.release_promote_packaging")
    for name in (
        "_read_manifest_from_zip",
        "_determine_version_from_rc_manifest",
        "_extract_zip_to_work_dir",
        "_inspect_rc_bundle_notes_manifest",
        "_prepare_packaging_work_dir",
        "_write_embedded_promote_reports",
        "_rebuild_promoted_zip",
        "_rebuild_promoted_zip_with_report",
    ):
        assert getattr(release_mod, name, None) is getattr(
            packaging_mod, name, None
        ), f"release promote packaging helper drifted: {name}"


def test_release_promote_packaging_module_surface_stays_focused() -> None:
    source_path = Path("mesh_cli/release_promote_packaging.py")
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))

    top_level_defs = [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    ]
    assert top_level_defs == [
        "_read_manifest_from_zip",
        "_determine_version_from_rc_manifest",
        "_extract_zip_to_work_dir",
        "_write_embedded_promote_reports",
        "_prepare_packaging_work_dir",
        "_inspect_rc_bundle_notes_manifest",
        "_rebuild_promoted_zip_with_report",
        "_rebuild_promoted_zip",
    ]
