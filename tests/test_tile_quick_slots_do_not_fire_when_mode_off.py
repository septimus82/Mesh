from __future__ import annotations

import arcade


def test_tile_quick_slots_do_not_fire_when_mode_off(capsys) -> None:
    from engine.input_runtime import capture as input_capture
    from engine.palette_mode import get_state
    from engine.tile_paint_mode import TilePaintState

    palette = get_state()
    original_enabled = bool(palette.enabled)
    palette.enabled = False
    try:
        class _Window:
            show_debug = True
            tile_paint_state = TilePaintState(enabled=False, layer_id="Ground", tile_id=7)
            entity_paint_state = type("EP", (), {"enabled": False})()
            capture_state = type("CS", (), {"enabled": False})()
            ui_controller = type("U", (), {"on_key_press": lambda *_a: False, "input_blocked": False})()
            console_controller = type("C", (), {"active": False, "toggle": lambda *_a: None})()
            editor_controller = type("E", (), {"active": False})()

        window = _Window()
        controller = type("Ctl", (), {"window": window, "manager": type("M", (), {"press": lambda *_a: None})(), "_keys": set()})()

        assert input_capture.handle_key_press(controller, arcade.key.KEY_1, arcade.key.MOD_ALT) is False
        assert capsys.readouterr().out.strip() == ""
    finally:
        palette.enabled = original_enabled

