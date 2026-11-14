from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]
from pathlib import Path


def test_verify_all_macro_audit_includes_new_objective_macro_case(verify_all_audit_artifacts: Path) -> None:
    artifacts_dir = verify_all_audit_artifacts  # (one verify-all of this checkout, shared: conftest.py)

    payload = json.loads((artifacts_dir / "macro_audit.json").read_text(encoding="utf-8"))
    assert payload["ok"] is True

    cases = payload["cases"]
    match = next((c for c in cases if c.get("macro_path") == "packs/core_regions/macros/objective_find_cellar.json"), None)
    assert match is not None
    assert match["scene_path"] == "scenes/door_interior.json"
    assert match["args"]["anchor"] == "player"
    assert match["args"]["zone_id"] == "demo_reached_interior_zone"
    assert match["args"]["set_flag"] == "demo.reached_interior"
    assert match["args"]["toast"] == "Objective: Find the cellar"
    assert int(match["will_create"]) >= 1
