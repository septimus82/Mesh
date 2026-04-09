from __future__ import annotations

import arcade

from tests._game_window_undo_stub import as_game_window


def test_entity_transform_skips_player_noop_when_only_player(capsys) -> None:
    from engine.entity_select_mode import EntitySelectState
    from engine.input_runtime import capture as input_capture
    from engine.palette_mode import get_state
    from engine.scene_controller import SceneController

    palette = get_state()
    original_enabled = bool(palette.enabled)
    palette.enabled = False
    try:
        window = type(
            "W",
            (),
            {
                "show_debug": True,
                "editor_controller": type("E", (), {"active": False})(),
                "ui_controller": type("U", (), {"on_key_press": lambda *_a: False, "input_blocked": False})(),
                "console_controller": type("C", (), {"active": False, "toggle": lambda *_a: None, "process_key": lambda *_a: False})(),
            },
        )()
        sc = SceneController(as_game_window(window))
        sc.current_scene_path = "scenes/foo.json"
        sc._loaded_scene_source_data = {"entities": [{"id": "p", "prefab_id": "player", "x": 1.0, "y": 2.0}]}
        window.scene_controller = sc
        window.entity_select_state = EntitySelectState(selected_ids=["p"], primary_id="p")

        controller = type("Ctl", (), {"window": window, "manager": type("M", (), {"press": lambda *_a: None})(), "_keys": set()})()
        capsys.readouterr()
        assert input_capture.handle_key_press(controller, arcade.key.E, arcade.key.MOD_CTRL) is True
        assert capsys.readouterr().out.strip() == "ENTITY_TRANSFORM noop reason=only_player"
    finally:
        palette.enabled = original_enabled
