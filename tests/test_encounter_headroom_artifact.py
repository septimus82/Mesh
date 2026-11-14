from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]
from pathlib import Path


def test_verify_all_writes_encounter_headroom_artifact(verify_all_audit_artifacts: Path) -> None:
    artifacts_dir = verify_all_audit_artifacts  # (one verify-all of this checkout, shared: conftest.py)

    path = artifacts_dir / "encounter_headroom.json"
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["scene_count"] >= 1
    rows = payload["rows"]
    assert isinstance(rows, list) and rows

    door_easy = next(
        (
            r
            for r in rows
            if r.get("scene_path") == "scenes/door_field.json" and str(r.get("difficulty") or "") == "easy"
        ),
        None,
    )
    assert door_easy is not None
    util = float(door_easy.get("utilization"))
    assert 0.0 <= util <= 1.5

    ashen_magma_easy = next(
        (
            r
            for r in rows
            if r.get("scene_path") == "packs/core_regions/scenes/Ashen_interior.json"
            and str(r.get("difficulty") or "") == "easy"
        ),
        None,
    )
    assert ashen_magma_easy is not None
    assert float(ashen_magma_easy.get("utilization")) <= 0.65

    ashen_void_easy = next(
        (
            r
            for r in rows
            if r.get("scene_path") == "packs/core_regions/scenes/Ashen_hub.json" and str(r.get("difficulty") or "") == "easy"
        ),
        None,
    )
    assert ashen_void_easy is not None
    assert float(ashen_void_easy.get("utilization")) <= 0.70
