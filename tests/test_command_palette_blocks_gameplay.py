from __future__ import annotations

import engine.optional_arcade as optional_arcade


def test_command_palette_blocks_gameplay() -> None:
    from engine.input_runtime import capture as input_capture
    from engine.palette_mode import get_state

    palette = get_state()
    original_enabled = bool(palette.enabled)
    palette.enabled = False
    try:
        pressed: list[int] = []

        class _Mgr:
            def press(self, key: int) -> None:
                pressed.append(int(key))

        class _Window:
            show_debug = True
            command_palette_enabled = True
            command_palette_query = ""
            command_palette_index = 0
            ui_controller = type("U", (), {"on_key_press": lambda *_a: False, "input_blocked": False})()
            console_controller = type("C", (), {"active": False, "toggle": lambda *_a: None})()
            editor_controller = type("E", (), {"active": False})()

        window = _Window()
        controller = type("Ctl", (), {"window": window, "manager": _Mgr(), "_keys": set()})()

        # Keys are consumed and do not route to InputManager.
        assert input_capture.handle_key_press(controller, optional_arcade.arcade.key.W, 0) is True
        assert pressed == []

        # Mouse press is consumed.
        assert input_capture.handle_mouse_press(controller, 10.0, 10.0, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True
        assert pressed == []
    finally:
        palette.enabled = original_enabled

