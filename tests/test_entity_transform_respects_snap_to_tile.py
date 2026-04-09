from __future__ import annotations

import arcade

from tests._game_window_undo_stub import as_game_window, bind_game_window_undo_methods


def test_entity_transform_respects_snap_to_tile(capsys) -> None:
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
                "scene_dirty_counter": 0,
                "scene_dirty_reason": "",
                "scene_dirty": False,
                "undo_stack": [],
                "redo_stack": [],
                "_undo_ts_counter": 0,
                "_undo_suppress_count": 0,
                "entity_snap_to_tile": True,
                "editor_controller": type("E", (), {"active": False})(),
                "ui_controller": type("U", (), {"on_key_press": lambda *_a: False, "input_blocked": False})(),
                "console_controller": type("C", (), {"active": False, "toggle": lambda *_a: None, "process_key": lambda *_a: False})(),
            },
        )()

        bind_game_window_undo_methods(window)
        sc = SceneController(as_game_window(window))
        sc.current_scene_path = "scenes/foo.json"
        sc._loaded_scene_source_data = {
            "tilemap": {"width": 4, "height": 4, "tilewidth": 16, "tileheight": 16, "tile_layers": []},
            "entities": [
                {"id": "a", "prefab_id": "slime_blob", "x": 8.0, "y": 8.0},
                {"id": "b", "prefab_id": "slime_blob", "x": 24.0, "y": 8.0},
            ],
        }
        window.scene_controller = sc
        window.entity_select_state = EntitySelectState(selected_ids=["a", "b"], primary_id="a")
        controller = type("Ctl", (), {"window": window, "manager": type("M", (), {"press": lambda *_a: None})(), "_keys": set()})()
        capsys.readouterr()

        assert input_capture.handle_key_press(controller, arcade.key.E, arcade.key.MOD_CTRL) is True
        assert capsys.readouterr().out.strip() == "ENTITY_ROTATE ok count=2"

        entities = sc.get_authored_scene_payload()["entities"]
        a = next(e for e in entities if e["id"] == "a")
        b = next(e for e in entities if e["id"] == "b")
        assert (a["x"], a["y"]) == (24.0, 24.0)
        assert (b["x"], b["y"]) == (24.0, 8.0)
    finally:
        palette.enabled = original_enabled
