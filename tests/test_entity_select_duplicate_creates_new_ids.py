from __future__ import annotations

import arcade


def test_entity_select_duplicate_creates_new_ids(capsys) -> None:
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
                "entity_snap_to_tile": False,
            },
        )()

        sc = SceneController(window)  # type: ignore[arg-type]
        sc.current_scene_path = "scenes/foo.json"
        sc._loaded_scene_source_data = {
            "entities": [
                {"id": "a", "prefab_id": "slime_blob", "x": 1.0, "y": 2.0, "name": "A"},
                {"id": "b", "prefab_id": "slime_blob", "x": 10.0, "y": 20.0},
            ]
        }
        window.scene_controller = sc

        window.entity_select_state = EntitySelectState(selected_ids=["a", "b"], primary_id="b")
        controller = type("Ctl", (), {"window": window, "manager": type("M", (), {"press": lambda *_a: None})(), "_keys": set()})()

        assert input_capture.handle_key_press(controller, arcade.key.D, arcade.key.MOD_CTRL) is True
        assert capsys.readouterr().out.strip() == "ENTITY_DUPLICATE ok count=2 dx=16.0 dy=16.0"

        entities = sc.get_authored_scene_payload()["entities"]
        ids = sorted(e["id"] for e in entities)
        assert "a__dup1" in ids
        assert "b__dup1" in ids

        dup_a = next(e for e in entities if e["id"] == "a__dup1")
        assert dup_a["x"] == 17.0
        assert dup_a["y"] == 18.0
        assert dup_a["name"] == "A"

        assert window.entity_select_state.selected_ids == ["a__dup1", "b__dup1"]
        assert window.entity_select_state.primary_id == "b__dup1"
    finally:
        palette.enabled = original_enabled

