from __future__ import annotations

import json
from pathlib import Path


def test_ridge_outpost_hub_has_hard_shadows_light_and_occluders() -> None:
    scene_path = "packs/core_regions/scenes/Ridge Outpost_hub.json"
    payload = json.loads(Path(scene_path).read_text(encoding="utf-8"))

    settings = payload.get("settings")
    assert isinstance(settings, dict)
    assert settings.get("lighting_shadows_mode") == "hard"

    occluders = payload.get("occluders")
    assert isinstance(occluders, list)
    assert len(occluders) >= 1
    assert any(float(o.get("width") or 0.0) >= 16.0 and float(o.get("height") or 0.0) >= 16.0 for o in occluders if isinstance(o, dict))

    lights = payload.get("lights")
    assert isinstance(lights, list)
    assert len(lights) >= 1

    entities = payload.get("entities")
    assert isinstance(entities, list)
    player = next((e for e in entities if isinstance(e, dict) and e.get("tag") == "player" and e.get("name") == "Player"), None)
    assert isinstance(player, dict)
    behaviour_config = player.get("behaviour_config")
    assert isinstance(behaviour_config, dict)
    assert "LightSource" in behaviour_config

    behaviours = player.get("behaviours")
    assert isinstance(behaviours, list)
    assert any(isinstance(b, dict) and b.get("type") == "LightSource" for b in behaviours)
