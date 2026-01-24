from __future__ import annotations

import arcade


def test_entity_select_box_select_union_and_subtract() -> None:
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

        sprites = [_Sprite("a", 5, 5), _Sprite("b", 15, 15), _Sprite("c", 50, 50)]

        class _Scene:
            all_sprites = sprites

        def _provider(_window):
            return {"hover": {}}

        window = type(
            "W",
            (),
            {
                "show_debug": True,
                "entity_select_state": EntitySelectState(selected_ids=["c"], primary_id="c"),
                "scene_controller": _Scene(),
                "scene_inspector_overlay": type("O", (), {"provider": staticmethod(_provider)})(),
                "editor_controller": type("E", (), {"active": False, "handle_mouse_click": lambda *_a: False, "handle_mouse_drag": lambda *_a: False})(),
                "screen_to_world": staticmethod(lambda x, y: (float(x), float(y))),
                "mark_scene_dirty": lambda *_a, **_k: None,
            },
        )()
        controller = type("C", (), {"window": window, "_mouse_x": 0.0, "_mouse_y": 0.0})()

        assert input_capture.handle_mouse_press(controller, 0, 0, arcade.MOUSE_BUTTON_LEFT, 0) is True
        input_capture.handle_mouse_drag(controller, 20, 20, 0, 0, arcade.MOUSE_BUTTON_LEFT, 0)
        assert input_capture.handle_mouse_release(controller, 20, 20, arcade.MOUSE_BUTTON_LEFT, arcade.key.MOD_SHIFT) is True
        assert window.entity_select_state.selected_ids == ["a", "b", "c"]

        assert input_capture.handle_mouse_press(controller, 0, 0, arcade.MOUSE_BUTTON_LEFT, 0) is True
        input_capture.handle_mouse_drag(controller, 20, 20, 0, 0, arcade.MOUSE_BUTTON_LEFT, 0)
        assert input_capture.handle_mouse_release(controller, 20, 20, arcade.MOUSE_BUTTON_LEFT, arcade.key.MOD_CTRL) is True
        assert window.entity_select_state.selected_ids == ["c"]
    finally:
        palette.enabled = original_enabled

