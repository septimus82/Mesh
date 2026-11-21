from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]
from pathlib import Path


def test_verify_all_writes_stamp_audit_artifact(verify_all_audit_artifacts: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    artifacts_dir = verify_all_audit_artifacts  # (one verify-all of this checkout, shared: conftest.py)

    path = artifacts_dir / "stamp_audit.json"
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert int(payload["case_count"]) >= 1
    cases = payload["cases"]
    assert isinstance(cases, list) and cases

    expected = json.loads((repo_root / "worlds" / "main_world.json").read_text(encoding="utf-8"))["stamp_audit_cases"][0]
    expected_scene = expected["scene_path"]
    expected_stamp = expected["stamp_path"]

    match = next(
        (c for c in cases if c.get("scene_path") == expected_scene and c.get("stamp_path") == expected_stamp),
        None,
    )
    assert match is not None
    assert match["origin"] == expected["origin"]
    assert match.get("id_prefix") == expected.get("id_prefix")

    assert int(match["tile_change_count"]) == 90
    assert int(match["entity_change_count"]) == 2
    assert len(match["tile_changes"]) == 90
    assert len(match["tile_changes"]) <= 200

    assert match["entity_changes"] == [
        {
            "action": "add",
            "id": "stamp_audit_sandbox_audit_torch1_1_1_0_0",
            "prefab_id": "torch_wisp",
            "x": 56.0,
            "y": 56.0,
        },
        {
            "action": "add",
            "id": "stamp_audit_sandbox_audit_torch2_1_1_0_0",
            "prefab_id": "torch_wisp",
            "x": 136.0,
            "y": 56.0,
        },
    ]
