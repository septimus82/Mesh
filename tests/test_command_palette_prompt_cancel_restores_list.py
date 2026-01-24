from __future__ import annotations

import engine.optional_arcade as optional_arcade


def test_command_palette_prompt_cancel_restores_list(monkeypatch) -> None:
    from engine.input_runtime import capture as input_capture
    from engine.palette_mode import get_state

    palette = get_state()
    original_enabled = bool(palette.enabled)
    palette.enabled = False
    try:
        class _SceneController:
            current_scene_path = "scenes/foo.json"

        class _Window:
            show_debug = True
            scene_persist_armed = True
            command_palette_enabled = True
            command_palette_query = "save"
            command_palette_index = 0
            command_palette_prompt_active = False
            scene_controller = _SceneController()
            ui_controller = type("U", (), {"on_key_press": lambda *_a: False, "input_blocked": False})()
            console_controller = type("C", (), {"active": False, "toggle": lambda *_a: None})()
            editor_controller = type("E", (), {"active": False})()

            @staticmethod
            def save_scene_as(_arg: str):
                raise AssertionError("should not run on cancel")

        window = _Window()
        controller = type("Ctl", (), {"window": window, "manager": type("M", (), {"press": lambda *_a: None})(), "_keys": set()})()

        assert input_capture.handle_key_press(controller, optional_arcade.arcade.key.ENTER, 0) is True
        assert window.command_palette_prompt_active is True

        assert input_capture.handle_key_press(controller, optional_arcade.arcade.key.ESCAPE, 0) is True
        assert window.command_palette_enabled is True
        assert window.command_palette_prompt_active is False
    finally:
        palette.enabled = original_enabled

