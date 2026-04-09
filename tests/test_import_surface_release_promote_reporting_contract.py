from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest


pytestmark = [pytest.mark.fast]


def test_release_promote_reporting_helpers_remain_patchable_from_release_module() -> None:
    release_mod = importlib.import_module("mesh_cli.release")
    reporting_mod = importlib.import_module("mesh_cli.release_promote_reporting")
    for name in (
        "_build_promote_report",
        "_format_promote_report_text",
        "_promote_report_paths",
        "_set_promote_version",
        "_summarize_verify_report",
        "_set_promote_verify_summary",
        "_write_promote_reports",
    ):
        assert getattr(release_mod, name, None) is getattr(
            reporting_mod, name, None
        ), f"release promote reporting helper drifted: {name}"


def test_release_promote_reporting_module_surface_stays_focused() -> None:
    source_path = Path("mesh_cli/release_promote_reporting.py")
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))

    top_level_defs = [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    ]
    assert top_level_defs == [
        "_build_promote_report",
        "_set_promote_version",
        "_set_promote_verify_summary",
        "_promote_report_paths",
        "_summarize_verify_report",
        "_format_promote_report_text",
        "_write_promote_reports",
    ]


def test_release_promote_reporting_writer_uses_release_patch_seams(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release_mod = importlib.import_module("mesh_cli.release")
    reporting_mod = importlib.import_module("mesh_cli.release_promote_reporting")

    monkeypatch.setattr(release_mod, "_format_promote_report_text", lambda _report: "patched\n")

    out_zip = tmp_path / "release_final.zip"
    _, txt_path = reporting_mod._write_promote_reports(out_zip, {"ok": True})

    assert txt_path.read_text(encoding="utf-8") == "patched\n"
