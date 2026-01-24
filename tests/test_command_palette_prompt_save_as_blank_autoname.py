from __future__ import annotations

import engine.optional_arcade as optional_arcade


def test_command_palette_prompt_save_as_blank_autoname(capsys, monkeypatch) -> None:
    from engine.input_runtime import capture as input_capture
    from engine.palette_mode import get_state

    palette = get_state()
    original_enabled = bool(palette.enabled)
    palette.enabled = False
    try:
        called: list[str] = []

        class _Result:
            ok = True
            path = "scenes/foo__v001.json"

        def _save_scene_as(arg: str):
            called.append(arg)
            return _Result()

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

            save_scene_as = staticmethod(_save_scene_as)

        window = _Window()
        controller = type("Ctl", (), {"window": window, "manager": type("M", (), {"press": lambda *_a: None})(), "_keys": set()})()

        # Enter should open prompt for Save As (default empty).
        assert input_capture.handle_key_press(controller, optional_arcade.arcade.key.ENTER, 0) is True
        assert window.command_palette_prompt_active is True
        assert str(getattr(window, "command_palette_prompt_text", "")) == ""

        # Confirm with blank.
        assert input_capture.handle_key_press(controller, optional_arcade.arcade.key.ENTER, 0) is True
        out = capsys.readouterr().out.strip().splitlines()
        assert out[-1] == "PALETTE_RUN ok id=scene.save_as title=Save Scene As (auto version)"
        assert called == [""]
    finally:
        palette.enabled = original_enabled

