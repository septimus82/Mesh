from __future__ import annotations

import arcade


def test_scene_save_as_requires_armed(capsys) -> None:
    from engine.input_runtime import capture as input_capture
    from engine.palette_mode import get_state

    palette = get_state()
    original_enabled = bool(palette.enabled)
    palette.enabled = False
    try:
        class _SceneController:
            current_scene_path = "scenes/foo.json"

            def get_authored_scene_payload(self) -> dict:
                return {"entities": []}

        class _Window:
            show_debug = True
            scene_persist_armed = False
            scene_controller = _SceneController()
            editor_controller = type("E", (), {"active": False})()
            ui_controller = type("U", (), {"input_blocked": False, "on_key_press": lambda *_a: False})()
            console_controller = type("C", (), {"active": False, "toggle": lambda *_a: None})()
            tile_paint_state = type("TP", (), {"enabled": False})()
            entity_paint_state = type("EP", (), {"enabled": False})()
            capture_state = type("CS", (), {"enabled": False})()

        window = _Window()
        controller = type("Ctl", (), {"window": window, "manager": type("M", (), {"press": lambda *_a: None})(), "_keys": set()})()

        assert input_capture.handle_key_press(controller, arcade.key.A, arcade.key.MOD_CTRL | arcade.key.MOD_SHIFT) is True
        assert capsys.readouterr().out.strip() == "SCENE_SAVE_AS (not armed)"
    finally:
        palette.enabled = original_enabled
