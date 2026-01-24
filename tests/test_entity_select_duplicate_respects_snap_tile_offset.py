from __future__ import annotations

import arcade


def test_entity_select_duplicate_respects_snap_tile_offset(capsys) -> None:
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
                "mark_scene_dirty": lambda self, reason: setattr(self, "scene_dirty_counter", int(getattr(self, "scene_dirty_counter", 0)) + 1),
                "console_controller": type("C", (), {"active": False})(),
                "ui_controller": type("U", (), {"on_key_press": lambda *_a: False, "input_blocked": False})(),
                "editor_controller": type("E", (), {"active": False})(),
                "scene_inspector_overlay": type("O", (), {"visible": False})(),
                "entity_snap_to_tile": True,
            },
        )()

        sc = SceneController(window)  # type: ignore[arg-type]
        sc.current_scene_path = "scenes/foo.json"
        sc._loaded_scene_source_data = {
            "tilemap": {"width": 1, "height": 1, "tilewidth": 32, "tileheight": 48},
            "entities": [{"id": "a", "prefab_id": "slime_blob", "x": 0.0, "y": 0.0}],
        }
        window.scene_controller = sc

        window.entity_select_state = EntitySelectState(selected_ids=["a"], primary_id="a")
        controller = type("Ctl", (), {"window": window, "manager": type("M", (), {"press": lambda *_a: None})(), "_keys": set()})()

        assert input_capture.handle_key_press(controller, arcade.key.D, arcade.key.MOD_CTRL) is True
        assert capsys.readouterr().out.strip() == "ENTITY_DUPLICATE ok count=1 dx=32.0 dy=48.0"

        entities = sc.get_authored_scene_payload()["entities"]
        dup = next(e for e in entities if e["id"] == "a__dup1")
        assert dup["x"] == 32.0
        assert dup["y"] == 48.0
    finally:
        palette.enabled = original_enabled

