from __future__ import annotations

from unittest.mock import MagicMock


def test_gated_scene_transition_not_triggered() -> None:
    from engine.behaviours.scene_transition import SceneTransition

    entity = MagicMock()
    entity.mesh_name = "Door"
    entity.mesh_entity_data = {"id": "door", "require_flags": ["demo.x"]}

    actor = MagicMock()
    actor.mesh_name = "Player"

    window = MagicMock()
    window.set_next_spawn_point = MagicMock()
    window.emit_signal = MagicMock()
    window.request_scene_change = MagicMock()

    def get_flag_false(name: str, default: bool = False) -> bool:
        return False

    window.get_flag = get_flag_false

    behaviour = SceneTransition(entity, window, target_scene="scenes/next.json", spawn_id="spawn_a", allow_interact=True)
    behaviour.on_interact(window, actor)
    window.request_scene_change.assert_not_called()

    def get_flag_true(name: str, default: bool = False) -> bool:
        return True

    window.get_flag = get_flag_true
    behaviour.on_interact(window, actor)
    window.request_scene_change.assert_called_with("scenes/next.json")

