from __future__ import annotations

import json
from pathlib import Path


def _find_entity(payload: dict, entity_id: str) -> dict:
    entities = payload.get("entities")
    assert isinstance(entities, list)
    ent = next((e for e in entities if isinstance(e, dict) and e.get("id") == entity_id), None)
    assert isinstance(ent, dict)
    return ent


def test_guard_patrol_chase_demo_scene_has_guard_waypoints_and_wall() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    payload = json.loads((repo_root / "scenes" / "guard_patrol_chase_demo.json").read_text(encoding="utf-8"))
    assert isinstance(payload, dict)

    guard = _find_entity(payload, "guard_patrol_chase_demo_guard_80_80_0_0")
    bcfg = guard.get("behaviour_config")
    assert isinstance(bcfg, dict)
    pcfg = bcfg.get("PatrolChase")
    assert isinstance(pcfg, dict)
    assert pcfg.get("los_required") is True
    assert pcfg.get("stop_range_tiles") == 1
    assert pcfg.get("return_to_patrol") is True
    assert pcfg.get("resume_waypoint_mode") == "nearest"
    assert pcfg.get("target_tag") == "player"
    assert pcfg.get("patrol_tag") == "patrol_waypoint"

    entities = payload.get("entities")
    assert isinstance(entities, list)
    waypoints = [e for e in entities if isinstance(e, dict) and e.get("tag") == "patrol_waypoint"]
    assert len(waypoints) >= 2

    tilemap = payload.get("tilemap")
    assert isinstance(tilemap, dict)
    assert tilemap.get("path") == "assets/tilemaps/demo_map.json"
    assert tilemap.get("collision_layer_id") == "platforms"

    overrides = tilemap.get("overrides")
    assert isinstance(overrides, dict)
    layers = overrides.get("layers")
    assert isinstance(layers, dict)
    platforms = layers.get("platforms")
    assert isinstance(platforms, list)
    assert len(platforms) == 12 * 8
    assert sum(1 for v in platforms if int(v) != 0) >= 5
