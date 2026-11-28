from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]
from pathlib import Path


def test_verify_all_writes_brush_audit_artifact(verify_all_audit_artifacts: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    artifacts_dir = verify_all_audit_artifacts  # (one verify-all of this checkout, shared: conftest.py)

    path = artifacts_dir / "brush_audit.json"
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert int(payload["case_count"]) >= 1
    cases = payload["cases"]
    assert isinstance(cases, list) and cases

    expected = json.loads((repo_root / "worlds" / "main_world.json").read_text(encoding="utf-8"))["brush_audit_cases"][0]
    expected_scene = expected["scene_path"]
    expected_brush = expected["brush_path"]

    match = next(
        (c for c in cases if c.get("scene_path") == expected_scene and c.get("brush_path") == expected_brush),
        None,
    )
    assert match is not None
    assert match["origin"] == expected["origin"]
    assert match["layer_id"] == expected["layer_id"]
    assert match["anchor"] == expected["anchor"]
    assert match["clip"] == expected["clip"]

    assert int(match["tile_change_count"]) == 8
    assert len(match["tile_changes"]) == 8
    assert len(match["tile_changes"]) <= 200

    assert match["tile_changes"][:3] == [
        {"after": 12, "before": 0, "layer_id": "Ground", "x": 1, "y": 1},
        {"after": 13, "before": 0, "layer_id": "Ground", "x": 2, "y": 1},
        {"after": 14, "before": 0, "layer_id": "Ground", "x": 3, "y": 1},
    ]
