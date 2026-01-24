from __future__ import annotations

import json
from pathlib import Path


def _patrol_chase_entities(payload: dict) -> list[dict]:
    out: list[dict] = []
    for ent in payload.get("entities") or []:
        if not isinstance(ent, dict):
            continue
        cfg_root = ent.get("behaviour_config")
        cfg = cfg_root.get("PatrolChase") if isinstance(cfg_root, dict) else None
        if isinstance(cfg, dict):
            out.append(ent)
    return out


def test_guard_patrol_chase_duo_demo_scene_has_two_guards_two_patrol_sets_and_wall() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    payload = json.loads((repo_root / "scenes" / "guard_patrol_chase_duo_demo.json").read_text(encoding="utf-8"))
    assert isinstance(payload, dict)

    guards = _patrol_chase_entities(payload)
    assert len(guards) == 2

    patrol_tags: set[str] = set()
    for guard in guards:
        bcfg = guard.get("behaviour_config")
        assert isinstance(bcfg, dict)
        pcfg = bcfg.get("PatrolChase")
        assert isinstance(pcfg, dict)
        assert pcfg.get("los_required") is True
        assert pcfg.get("stop_range_tiles") == 1
        assert pcfg.get("target_tag") == "player"
        assert pcfg.get("acquire_radius_tiles") == 8
        assert pcfg.get("leash_radius_tiles") == 12
        assert pcfg.get("give_up_ticks") == 20
        assert pcfg.get("cooldown_ticks") == 30
        patrol_tag = pcfg.get("patrol_tag")
        assert isinstance(patrol_tag, str) and patrol_tag
        patrol_tags.add(patrol_tag)

    assert patrol_tags == {"patrol_waypoint_a", "patrol_waypoint_b"}

    entities = payload.get("entities")
    assert isinstance(entities, list)
    for tag in sorted(patrol_tags):
        waypoints = [e for e in entities if isinstance(e, dict) and e.get("tag") == tag]
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

