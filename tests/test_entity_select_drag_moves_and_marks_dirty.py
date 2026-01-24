from __future__ import annotations

import arcade


def test_entity_select_drag_moves_and_marks_dirty(monkeypatch) -> None:
    from engine.entity_select_mode import EntitySelectState
    from engine.input_runtime import capture as input_capture
    from engine.palette_mode import get_state

    palette = get_state()
    original_enabled = bool(palette.enabled)
    palette.enabled = False

    try:
        class _Sprite:
            center_x = 10.0
            center_y = 10.0
            mesh_entity_data = {"id": "e1", "prefab_id": "slime_blob", "x": 10.0, "y": 10.0}

        sprite = _Sprite()

        def _provider(_window):
            return {"hover": {"id": "e1", "prefab_id": "slime_blob"}}

        class _Scene:
            def debug_move_entity_by_id(self, entity_id: str, *, x: float, y: float) -> bool:
                if entity_id != "e1":
                    return False
                sprite.center_x = float(x)
                sprite.center_y = float(y)
                sprite.mesh_entity_data["x"] = float(x)
                sprite.mesh_entity_data["y"] = float(y)
                return True

            def debug_find_sprite_by_entity_id(self, entity_id: str):
                return sprite if entity_id == "e1" else None

        class _Window:
            show_debug = True
            entity_snap_to_tile = False
            scene_controller = _Scene()
            editor_controller = type("E", (), {"active": False, "handle_mouse_drag": lambda *_a: False, "handle_mouse_click": lambda *_a: False})()
            scene_inspector_overlay = type("O", (), {"provider": staticmethod(_provider)})()
            entity_select_state = EntitySelectState()

            def __init__(self) -> None:
                self.scene_dirty = False
                self.scene_dirty_reason = ""
                self.scene_dirty_counter = 0

            def screen_to_world(self, x: float, y: float):
                return float(x), float(y)

            def mark_scene_dirty(self, reason: str) -> None:
                self.scene_dirty = True
                self.scene_dirty_reason = str(reason)
                self.scene_dirty_counter += 1

        window = _Window()
        controller = type("C", (), {"window": window, "_mouse_x": 0.0, "_mouse_y": 0.0})()

        assert input_capture.handle_mouse_press(controller, 10, 10, arcade.MOUSE_BUTTON_LEFT, 0) is True
        input_capture.handle_mouse_drag(controller, 50, 60, 0, 0, arcade.MOUSE_BUTTON_LEFT, 0)
        assert sprite.center_x == 50.0
        assert sprite.center_y == 60.0
        assert window.scene_dirty is True
        assert window.scene_dirty_reason == "entity_select_multi"
        assert window.scene_dirty_counter == 1

        assert input_capture.handle_mouse_release(controller, 50, 60, arcade.MOUSE_BUTTON_LEFT, 0) is True
        assert window.entity_select_state.dragging is False
    finally:
        palette.enabled = original_enabled
