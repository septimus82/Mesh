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


def test_micro_stealth_completion_room_is_reachable_from_upper_hall() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    world = json.loads((repo_root / "worlds" / "main_world.json").read_text(encoding="utf-8"))

    assert "micro_stealth_completion_room" in world["scenes"]
    assert (
        world["scenes"]["micro_stealth_completion_room"]["path"].replace("\\", "/")
        == "scenes/micro_stealth_completion_room.json"
    )

    links = world["links"]
    assert {
        "from": "upper_hall",
        "to": "micro_stealth_completion_room",
        "via": "MicroStealthCompletionDoor",
    } in links
    assert {
        "from": "micro_stealth_completion_room",
        "to": "upper_hall",
        "via": "MicroStealthCompletionReturnDoor",
    } in links

    upper_hall = json.loads((repo_root / "scenes" / "upper_hall.json").read_text(encoding="utf-8"))
    room = json.loads((repo_root / "scenes" / "micro_stealth_completion_room.json").read_text(encoding="utf-8"))

    door = _find_entity_by_name(upper_hall, "MicroStealthCompletionDoor")
    assert door is not None
    cfg_root = door.get("behaviour_config")
    cfg = cfg_root.get("SceneTransition") if isinstance(cfg_root, dict) else None
    assert isinstance(cfg, dict)
    assert cfg.get("target_scene") == "scenes/micro_stealth_completion_room.json"
    assert cfg.get("spawn_id") == "default"
    assert "default" in _scene_spawn_ids(room)

    back = _find_entity_by_name(room, "MicroStealthCompletionReturnDoor")
    assert back is not None
    cfg_root = back.get("behaviour_config")
    cfg = cfg_root.get("SceneTransition") if isinstance(cfg_root, dict) else None
    assert isinstance(cfg, dict)
    assert cfg.get("target_scene") == "scenes/upper_hall.json"
    assert cfg.get("spawn_id") == "upper_return"
    assert "upper_return" in _scene_spawn_ids(upper_hall)

