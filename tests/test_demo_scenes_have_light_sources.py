from __future__ import annotations

import json
from pathlib import Path


def _scene_has_light_source(scene_path: str) -> bool:
    payload = json.loads(Path(scene_path).read_text(encoding="utf-8"))
    for entity in payload.get("entities", []):
        if not isinstance(entity, dict):
            continue
        cfg = entity.get("behaviour_config")
        if isinstance(cfg, dict) and "LightSource" in cfg:
            return True
    return False


def test_demo_scenes_have_at_least_one_light_source_entity() -> None:
    scenes = [
        "scenes/guard_patrol_chase_demo.json",
        "scenes/guard_patrol_chase_duo_demo.json",
        "scenes/combat_tutorial_demo.json",
    ]
    for scene_path in scenes:
        assert _scene_has_light_source(scene_path), scene_path

