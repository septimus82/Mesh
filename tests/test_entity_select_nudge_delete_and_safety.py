from __future__ import annotations

import arcade


def test_entity_select_nudge_delete_and_safety(monkeypatch) -> None:
    from engine.entity_select_mode import EntitySelectState
    from engine.input_runtime import capture as input_capture
    from engine.palette_mode import get_state

    palette = get_state()
    original_enabled = bool(palette.enabled)
    palette.enabled = False

    try:
        class _Sprite:
            def __init__(self, entity_id: str, prefab_id: str) -> None:
                self.center_x = 10.0
                self.center_y = 20.0
                self.mesh_entity_data = {"id": entity_id, "prefab_id": prefab_id}

        sprites = {
            "e1": _Sprite("e1", "slime_blob"),
            "p1": _Sprite("p1", "player"),
        }

        class _Scene:
            def debug_find_sprite_by_entity_id(self, entity_id: str):
                return sprites.get(entity_id)

            def debug_move_entity_by_id(self, entity_id: str, *, x: float, y: float) -> bool:
                s = sprites.get(entity_id)
                if s is None:
                    return False
                s.center_x = float(x)
                s.center_y = float(y)
                return True

            def debug_remove_entity_by_id(self, entity_id: str) -> bool:
                s = sprites.get(entity_id)
                if s is None:
                    return False
                if s.mesh_entity_data.get("prefab_id") == "player":
                    return False
                del sprites[entity_id]
                return True

        class _Console:
            active = False

        class _UI:
            def on_key_press(self, _key: int, _mod: int) -> bool:
                return False

        window = type(
            "W",
            (),
            {
                "show_debug": True,
                "console_controller": _Console(),
                "ui_controller": _UI(),
                "editor_controller": type("E", (), {"active": False})(),
                "scene_inspector_overlay": type("O", (), {"visible": False})(),
                "scene_controller": _Scene(),
                "entity_select_state": EntitySelectState(selected_ids=["e1"], primary_id="e1"),
                "mark_scene_dirty": lambda *_a, **_k: None,
            },
        )()

        controller = type("C", (), {"window": window, "manager": type("M", (), {"press": lambda *_a: None})(), "_keys": set()})()

        assert input_capture.handle_key_press(controller, arcade.key.RIGHT, 0) is True
        assert sprites["e1"].center_x == 11.0
        assert sprites["e1"].center_y == 20.0

        assert input_capture.handle_key_press(controller, arcade.key.UP, arcade.key.MOD_SHIFT) is True
        assert sprites["e1"].center_x == 11.0
        assert sprites["e1"].center_y == 28.0

        assert input_capture.handle_key_press(controller, arcade.key.DELETE, 0) is True
        assert "e1" not in sprites
        assert window.entity_select_state.selected_ids == []
        assert window.entity_select_state.primary_id is None

        window.entity_select_state.selected_ids = ["p1"]
        window.entity_select_state.primary_id = "p1"
        assert input_capture.handle_key_press(controller, arcade.key.DELETE, 0) is True
        assert "p1" in sprites
        assert window.entity_select_state.selected_ids == []
        assert window.entity_select_state.primary_id is None
    finally:
        palette.enabled = original_enabled
