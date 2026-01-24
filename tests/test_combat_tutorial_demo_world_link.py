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


def test_combat_tutorial_demo_is_reachable_from_upper_hall() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    world = json.loads((repo_root / "worlds" / "main_world.json").read_text(encoding="utf-8"))

    assert "combat_tutorial_demo" in world["scenes"]
    assert world["scenes"]["combat_tutorial_demo"]["path"].replace("\\", "/") == "scenes/combat_tutorial_demo.json"

    links = world["links"]
    assert {"from": "upper_hall", "to": "combat_tutorial_demo", "via": "CombatTutorialDemoDoor"} in links
    assert {"from": "combat_tutorial_demo", "to": "upper_hall", "via": "CombatTutorialDemoReturnDoor"} in links

    upper_hall = json.loads((repo_root / "scenes" / "upper_hall.json").read_text(encoding="utf-8"))
    demo = json.loads((repo_root / "scenes" / "combat_tutorial_demo.json").read_text(encoding="utf-8"))

    door = _find_entity_by_name(upper_hall, "CombatTutorialDemoDoor")
    assert door is not None
    cfg_root = door.get("behaviour_config")
    cfg = cfg_root.get("SceneTransition") if isinstance(cfg_root, dict) else None
    assert isinstance(cfg, dict)
    assert cfg.get("target_scene") == "scenes/combat_tutorial_demo.json"
    assert cfg.get("spawn_id") == "default"
    assert "default" in _scene_spawn_ids(demo)

    back = _find_entity_by_name(demo, "CombatTutorialDemoReturnDoor")
    assert back is not None
    cfg_root = back.get("behaviour_config")
    cfg = cfg_root.get("SceneTransition") if isinstance(cfg_root, dict) else None
    assert isinstance(cfg, dict)
    assert cfg.get("target_scene") == "scenes/upper_hall.json"
    assert cfg.get("spawn_id") == "upper_return"
    assert "upper_return" in _scene_spawn_ids(upper_hall)


def test_upper_hall_has_combat_tutorial_markers() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    payload = json.loads((repo_root / "scenes" / "upper_hall.json").read_text(encoding="utf-8"))
    assert isinstance(payload, dict)

    complete = _find_entity_by_name(payload, "CombatTutorialComplete")
    assert complete is not None
    req = complete.get("require_flags")
    assert isinstance(req, list) and "demo.combat_tutorial_complete" in req

    claimed = _find_entity_by_name(payload, "CombatTutorialRewardClaimed")
    assert claimed is not None
    req = claimed.get("require_flags")
    assert isinstance(req, list) and "demo.combat_tutorial_reward_claimed" in req

    v2 = _find_entity_by_name(payload, "CombatTutorialV2Complete")
    assert v2 is not None
    req = v2.get("require_flags")
    assert isinstance(req, list) and "demo.combat_tutorial_v2_complete" in req
