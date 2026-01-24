from __future__ import annotations

import arcade


def test_tile_quick_slots_assign_and_select(capsys) -> None:
    from engine.input_runtime import capture as input_capture
    from engine.palette_mode import get_state
    from engine.tile_paint_mode import TilePaintState

    palette = get_state()
    original_enabled = bool(palette.enabled)
    palette.enabled = False
    try:
        class _Window:
            show_debug = True
            tile_paint_state = TilePaintState(enabled=True, layer_id="Ground", tile_id=17)
            entity_paint_state = type("EP", (), {"enabled": False})()
            capture_state = type("CS", (), {"enabled": False})()
            ui_controller = type("U", (), {"on_key_press": lambda *_a: False, "input_blocked": False})()
            console_controller = type("C", (), {"active": False, "toggle": lambda *_a: None})()
            editor_controller = type("E", (), {"active": False})()

        window = _Window()
        controller = type("Ctl", (), {"window": window, "manager": type("M", (), {"press": lambda *_a: None})(), "_keys": set()})()

        assert input_capture.handle_key_press(controller, arcade.key.KEY_1, arcade.key.MOD_ALT) is True
        assert capsys.readouterr().out.strip() == "TILE_SLOT_ASSIGN ok slot=1 tile=17"

        window.tile_paint_state.tile_id = 5
        assert input_capture.handle_key_press(controller, arcade.key.KEY_1, 0) is True
        assert capsys.readouterr().out.strip() == "TILE_SLOT_SELECT ok slot=1 tile=17"
        assert window.tile_paint_state.tile_id == 17
    finally:
        palette.enabled = original_enabled

