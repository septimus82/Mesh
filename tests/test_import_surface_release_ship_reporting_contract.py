from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest


pytestmark = [pytest.mark.fast]


def test_release_ship_reporting_helpers_remain_patchable_from_release_module() -> None:
    release_mod = importlib.import_module("mesh_cli.release")
    reporting_mod = importlib.import_module("mesh_cli.release_ship_reporting")
    for name in (
        "_build_ship_report",
        "_set_ship_verify_summary",
        "_set_ship_child_report_projection",
    ):
        assert getattr(release_mod, name, None) is getattr(
            reporting_mod, name, None
        ), f"release ship reporting helper drifted: {name}"


def test_release_ship_reporting_module_surface_stays_focused() -> None:
    source_path = Path("mesh_cli/release_ship_reporting.py")
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))

    top_level_defs = [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    ]
    assert top_level_defs == [
        "_build_ship_report",
        "_set_ship_verify_summary",
        "_set_ship_child_report_projection",
    ]


def test_release_ship_reporting_builder_uses_release_path_seams(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release_mod = importlib.import_module("mesh_cli.release")
    reporting_mod = importlib.import_module("mesh_cli.release_ship_reporting")

    monkeypatch.setattr(
        release_mod,
        "_rc_report_paths",
        lambda _zip_path: (tmp_path / "patched_rc.json", tmp_path / "patched_rc.txt"),
    )
    monkeypatch.setattr(
        release_mod,
        "_promote_report_paths",
        lambda _zip_path: (tmp_path / "patched_promote.json", tmp_path / "patched_promote.txt"),
    )
    monkeypatch.setattr(
        release_mod,
        "_ship_report_paths",
        lambda _out_dir: (tmp_path / "patched_ship.json", tmp_path / "patched_ship.txt"),
    )

    report = reporting_mod._build_ship_report(
        schema_version=1,
        out_dir=tmp_path,
        seed=123,
        bump_kind=None,
        do_tag=False,
        since=None,
        quiet=True,
        json_stdout=False,
        dry_run=False,
        provenance={},
        rc_zip=tmp_path / "rc_bundle.zip",
        final_zip=tmp_path / "release_final.zip",
    )

    assert report["artifacts"]["rc_report_json"] == "patched_rc.json"
    assert report["artifacts"]["promote_report_json"] == "patched_promote.json"
    assert report["artifacts"]["ship_report_json"] == "patched_ship.json"


def test_release_ship_reporting_verify_projection_uses_release_summary_seam(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release_mod = importlib.import_module("mesh_cli.release")
    reporting_mod = importlib.import_module("mesh_cli.release_ship_reporting")

    monkeypatch.setattr(
        release_mod,
        "_summarize_verify_report",
        lambda _verify_report: {"ok": True, "verified_count": 7},
    )

    report = {"verify": {"rc": {}, "final": {}}}
    reporting_mod._set_ship_verify_summary(report, key="rc", verify_report={"ok": False})

    assert report["verify"]["rc"] == {"ok": True, "verified_count": 7}
