from __future__ import annotations

import arcade


def test_entity_select_group_drag_moves_all_by_delta() -> None:
    from engine.entity_select_mode import EntitySelectState
    from engine.input_runtime import capture as input_capture
    from engine.palette_mode import get_state

    palette = get_state()
    original_enabled = bool(palette.enabled)
    palette.enabled = False
    try:
        class _Sprite:
            def __init__(self, entity_id: str, x: float, y: float) -> None:
                self.center_x = float(x)
                self.center_y = float(y)
                self.mesh_entity_data = {"id": entity_id, "prefab_id": "slime_blob"}

        sprites = {"a": _Sprite("a", 0, 0), "b": _Sprite("b", 10, 0)}

        def _provider(_window):
            return {"hover": {"id": "b", "prefab_id": "slime_blob"}}

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

        class _Window:
            show_debug = True
            entity_snap_to_tile = False
            entity_select_state = EntitySelectState(selected_ids=["a", "b"], primary_id="a")
            scene_controller = _Scene()
            scene_inspector_overlay = type("O", (), {"provider": staticmethod(_provider)})()
            editor_controller = type("E", (), {"active": False, "handle_mouse_drag": lambda *_a: False, "handle_mouse_click": lambda *_a: False})()

            def __init__(self) -> None:
                self.scene_dirty_reason = ""
                self.scene_dirty_counter = 0

            def screen_to_world(self, x: float, y: float):
                return float(x), float(y)

            def mark_scene_dirty(self, reason: str) -> None:
                self.scene_dirty_reason = str(reason)
                self.scene_dirty_counter += 1

        window = _Window()
        controller = type("C", (), {"window": window, "_mouse_x": 0.0, "_mouse_y": 0.0})()

        assert input_capture.handle_mouse_press(controller, 10, 0, arcade.MOUSE_BUTTON_LEFT, 0) is True
        input_capture.handle_mouse_drag(controller, 20, 5, 0, 0, arcade.MOUSE_BUTTON_LEFT, 0)
        assert sprites["b"].center_x == 20.0
        assert sprites["b"].center_y == 5.0
        assert sprites["a"].center_x == 10.0
        assert sprites["a"].center_y == 5.0
        assert window.scene_dirty_reason == "entity_select_multi"
        assert window.scene_dirty_counter == 1
    finally:
        palette.enabled = original_enabled

