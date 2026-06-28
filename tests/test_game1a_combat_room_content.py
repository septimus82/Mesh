from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.fast

SCENE_PATH = Path("scenes/game1a_combat_room.json")


def _load_scene() -> dict:
    return json.loads(SCENE_PATH.read_text(encoding="utf-8"))


def test_game1a_combat_room_has_player_enemies_and_encounter_watcher() -> None:
    scene = _load_scene()
    entities = scene.get("entities", [])

    player = next(entity for entity in entities if entity.get("id") == "game1a_player")
    assert {"PlayerController", "Health", "Combat"}.issubset(set(player.get("behaviours") or []))
    assert player.get("tag") == "player"

    enemies = [entity for entity in entities if entity.get("tag") == "enemy"]
    assert len(enemies) >= 2
    for enemy in enemies:
        assert {"EnemyAI", "Health", "Combat"}.issubset(set(enemy.get("behaviours") or []))
        assert enemy.get("prefab_id") == "chaser_enemy"

    controller = next(entity for entity in entities if entity.get("id") == "game1a_encounter_controller")
    assert "EncounterCleared" in (controller.get("behaviours") or [])
    watcher_cfg = controller["behaviour_config"]["EncounterCleared"]
    assert watcher_cfg["enemy_tag"] == "enemy"
    assert watcher_cfg["clear_event"] == "encounter_cleared"

    state_cfg = controller["behaviour_config"]["SetGameStateOnEvent"]
    assert state_cfg["event_type"] == "encounter_cleared"
    assert state_cfg["set_flags"]["game1a.victory"] is True

    emit_cfg = controller["behaviour_config"]["EmitEventOnEvent"]
    assert emit_cfg["listen_event"] == "encounter_cleared"
    assert emit_cfg["emit_event"] == "victory"


def test_game1a_combat_room_validates_with_builtin_behaviours() -> None:
    from engine.behaviours import load_builtin_behaviours
    from engine.scene_loader import SceneLoader

    load_builtin_behaviours()
    loader = SceneLoader()
    report = loader.validate_scene(loader.apply_scene_defaults(_load_scene()))
    assert report.ok, report.errors
