from __future__ import annotations

import arcade


def test_entity_select_click_selects_and_clears(monkeypatch) -> None:
    from engine.entity_select_mode import EntitySelectState
    from engine.input_runtime import capture as input_capture
    from engine.palette_mode import get_state

    palette = get_state()
    original_enabled = bool(palette.enabled)
    palette.enabled = False

    try:
        def _provider(window):
            mx = getattr(window, "_mouse_x", 0)
            if int(mx) == 10:
                return {"hover": {"id": "e1", "prefab_id": "slime_blob"}}
            return {"hover": {}}

        window = type(
            "W",
            (),
            {
                "show_debug": True,
                "editor_controller": type("E", (), {"active": False, "handle_mouse_click": lambda *_a: False})(),
                "scene_inspector_overlay": type("O", (), {"provider": staticmethod(_provider)})(),
                "entity_select_state": EntitySelectState(),
                "mark_scene_dirty": lambda *_a, **_k: None,
                "screen_to_world": staticmethod(lambda x, y: (float(x), float(y))),
                "scene_controller": type(
                    "S",
                    (),
                    {
                        "debug_find_sprite_by_entity_id": staticmethod(
                            lambda entity_id: type("Sprite", (), {"center_x": 10.0, "center_y": 0.0, "mesh_entity_data": {"id": entity_id}})()
                        )
                    },
                )(),
            },
        )()
        controller = type("C", (), {"window": window})()

        assert input_capture.handle_mouse_press(controller, 10, 0, arcade.MOUSE_BUTTON_LEFT, 0) is True
        assert window.authoring_selected_entity_id == "e1"
        assert window.entity_select_state.selected_ids == ["e1"]
        assert window.entity_select_state.primary_id == "e1"

        assert input_capture.handle_mouse_release(controller, 10, 0, arcade.MOUSE_BUTTON_LEFT, 0) is True

        assert input_capture.handle_mouse_press(controller, 99, 0, arcade.MOUSE_BUTTON_LEFT, 0) is True
        assert input_capture.handle_mouse_release(controller, 99, 0, arcade.MOUSE_BUTTON_LEFT, 0) is True
        assert getattr(window, "authoring_selected_entity_id", None) is None
        assert window.entity_select_state.selected_ids == []
        assert window.entity_select_state.primary_id is None
    finally:
        palette.enabled = original_enabled
