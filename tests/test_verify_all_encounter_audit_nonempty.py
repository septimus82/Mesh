from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]
from pathlib import Path


def test_verify_all_encounter_audit_summary_is_nonempty(verify_all_audit_artifacts: Path) -> None:
    artifacts_dir = verify_all_audit_artifacts  # (one verify-all of this checkout, shared: conftest.py)

    audit_path = artifacts_dir / "encounter_audit_compact.json"
    assert audit_path.exists()
    payload = json.loads(audit_path.read_text(encoding="utf-8"))
    assert payload["scene_count"] >= 1
    assert payload["rows"]

    found_door_field_spawn = False
    found_cellar_spawn = False
    found_cellar_elite = False
    found_door_interior_spawn = False
    found_door_interior_mini_boss = False
    found_forge_scene_spawn = False
    found_magma_scene_spawn = False
    found_void_scene_mini_boss_easy = False
    for row in payload["rows"]:
        scene_path = row.get("scene_path")
        if int(row.get("spawn_count", 0)) < 1:
            continue
        if float(row.get("total_spawn_cost", 0.0)) <= 0.0:
            continue
        difficulty = str(row.get("difficulty") or "")

        if scene_path == "scenes/door_field.json":
            found_door_field_spawn = True
        if scene_path == "scenes/cellar.json":
            found_cellar_spawn = True
            if int(row.get("elite_count", 0)) >= 1:
                found_cellar_elite = True
        if scene_path == "scenes/door_interior.json":
            found_door_interior_spawn = True
            if int(row.get("mini_boss_count", 0)) >= 1:
                found_door_interior_mini_boss = True
        if scene_path == "packs/core_regions/scenes/Ashen_dungeon.json":
            found_forge_scene_spawn = True
        if scene_path == "packs/core_regions/scenes/Ashen_interior.json":
            found_magma_scene_spawn = True
        if scene_path == "packs/core_regions/scenes/Ashen_hub.json" and difficulty == "easy":
            if int(row.get("mini_boss_count", 0)) >= 1:
                found_void_scene_mini_boss_easy = True

    assert found_door_field_spawn
    assert found_cellar_spawn
    assert found_cellar_elite
    assert found_door_interior_spawn
    assert found_door_interior_mini_boss
    assert found_forge_scene_spawn
    assert found_magma_scene_spawn
    assert found_void_scene_mini_boss_easy
