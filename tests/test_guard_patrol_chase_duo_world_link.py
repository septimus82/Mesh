from __future__ import annotations

import json
from pathlib import Path


def _find_entity_by_name(scene_payload: dict, name: str) -> dict | None:
    for ent in scene_payload.get("entities") or []:
        if isinstance(ent, dict) and ent.get("name") == name:
            return ent
    return None


def _scene_spawn_ids(scene_payload: dict) -> set[str]:
    ids: set[str] = set()
    for ent in scene_payload.get("entities") or []:
        if not isinstance(ent, dict):
            continue
        if ent.get("tag") != "spawn_point":
            continue
        spawn_id = ent.get("spawn_id")
        if isinstance(spawn_id, str) and spawn_id.strip():
            ids.add(spawn_id.strip())
    return ids


def test_guard_patrol_chase_duo_demo_is_reachable_from_upper_hall() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    world = json.loads((repo_root / "worlds" / "main_world.json").read_text(encoding="utf-8"))

    assert "guard_patrol_chase_duo_demo" in world["scenes"]
    assert (
        world["scenes"]["guard_patrol_chase_duo_demo"]["path"].replace("\\", "/")
        == "scenes/guard_patrol_chase_duo_demo.json"
    )

    links = world["links"]
    assert {
        "from": "upper_hall",
        "to": "guard_patrol_chase_duo_demo",
        "via": "GuardPatrolChaseDuoDemoDoor",
    } in links
    assert {
        "from": "guard_patrol_chase_duo_demo",
        "to": "upper_hall",
        "via": "GuardPatrolChaseDuoDemoReturnDoor",
    } in links

    upper_hall = json.loads((repo_root / "scenes" / "upper_hall.json").read_text(encoding="utf-8"))
    demo = json.loads((repo_root / "scenes" / "guard_patrol_chase_duo_demo.json").read_text(encoding="utf-8"))

    door = _find_entity_by_name(upper_hall, "GuardPatrolChaseDuoDemoDoor")
    assert door is not None
    cfg_root = door.get("behaviour_config")
    cfg = cfg_root.get("SceneTransition") if isinstance(cfg_root, dict) else None
    assert isinstance(cfg, dict)
    assert cfg.get("target_scene") == "scenes/guard_patrol_chase_duo_demo.json"
    assert cfg.get("spawn_id") == "default"
    assert "default" in _scene_spawn_ids(demo)

    back = _find_entity_by_name(demo, "GuardPatrolChaseDuoDemoReturnDoor")
    assert back is not None
    cfg_root = back.get("behaviour_config")
    cfg = cfg_root.get("SceneTransition") if isinstance(cfg_root, dict) else None
    assert isinstance(cfg, dict)
    assert cfg.get("target_scene") == "scenes/upper_hall.json"
    assert cfg.get("spawn_id") == "upper_return"
    assert "upper_return" in _scene_spawn_ids(upper_hall)

