from __future__ import annotations

import importlib

import pytest


pytestmark = [pytest.mark.fast]


def test_release_reporting_helpers_remain_patchable_from_release_module() -> None:
    release_mod = importlib.import_module("mesh_cli.release")
    reporting_mod = importlib.import_module("mesh_cli.release_reporting")
    for name in (
        "_rc_step",
        "_rc_report_paths",
        "_write_rc_reports",
        "_ship_report_paths",
        "_write_ship_reports",
    ):
        assert getattr(release_mod, name, None) is getattr(
            reporting_mod, name, None
        ), f"release reporting helper drifted: {name}"
