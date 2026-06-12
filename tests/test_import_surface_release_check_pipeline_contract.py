from __future__ import annotations

import importlib

import pytest

pytestmark = [pytest.mark.fast]


def test_release_check_helpers_remain_patchable_from_release_module() -> None:
    release_mod = importlib.import_module("mesh_cli.release")
    pipeline_mod = importlib.import_module("mesh_cli.release_check_pipeline")
    for name in (
        "_run_step",
        "_run_verify_all",
        "_run_assets_audit",
        "_run_export_build",
        "_run_debug_bundle",
        "_step_record",
        "_write_report",
        "_write_summary",
        "_resolve_path",
    ):
        assert getattr(release_mod, name, None) is getattr(pipeline_mod, name, None), f"release helper drifted: {name}"
