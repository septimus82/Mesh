from __future__ import annotations

import arcade


def test_prefab_quick_slots_assign_and_select(capsys) -> None:
    from engine.entity_paint_mode import EntityPaintState, PrefabInfo, get_selected_prefab_id
    from engine.input_runtime import capture as input_capture
    from engine.palette_mode import get_state

    palette = get_state()
    original_enabled = bool(palette.enabled)
    palette.enabled = False
    try:
        state = EntityPaintState(
            enabled=True,
            prefabs=(PrefabInfo(prefab_id="crate", tags=()), PrefabInfo(prefab_id="slime_blob", tags=("enemy",))),
            filter_mode="all",
            selected_index=1,
        )

        class _Window:
            show_debug = True
            entity_paint_state = state
            tile_paint_state = type("TP", (), {"enabled": False})()
            capture_state = type("CS", (), {"enabled": False})()
            ui_controller = type("U", (), {"on_key_press": lambda *_a: False, "input_blocked": False})()
            console_controller = type("C", (), {"active": False, "toggle": lambda *_a: None})()
            editor_controller = type("E", (), {"active": False})()

        window = _Window()
        controller = type("Ctl", (), {"window": window, "manager": type("M", (), {"press": lambda *_a: None})(), "_keys": set()})()

        assert get_selected_prefab_id(state) == "slime_blob"
        assert input_capture.handle_key_press(controller, arcade.key.KEY_1, arcade.key.MOD_ALT) is True
        assert capsys.readouterr().out.strip() == "PREFAB_SLOT_ASSIGN ok slot=1 prefab=slime_blob"

        state.selected_index = 0
        assert get_selected_prefab_id(state) == "crate"
        assert input_capture.handle_key_press(controller, arcade.key.KEY_1, 0) is True
        assert capsys.readouterr().out.strip() == "PREFAB_SLOT_SELECT ok slot=1 prefab=slime_blob"
        assert get_selected_prefab_id(state) == "slime_blob"
    finally:
        palette.enabled = original_enabled

