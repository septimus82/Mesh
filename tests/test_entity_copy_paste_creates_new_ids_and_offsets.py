from __future__ import annotations

import arcade


def test_entity_copy_paste_creates_new_ids_and_offsets(capsys) -> None:
    from engine.entity_select_mode import EntitySelectState
    from engine.game import GameWindow
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
                "scene_dirty": False,
                "scene_dirty_reason": "",
                "scene_dirty_counter": 0,
                "undo_stack": [],
                "redo_stack": [],
                "_undo_ts_counter": 0,
                "_undo_suppress_count": 0,
                "entity_snap_to_tile": False,
                "editor_controller": type("E", (), {"active": False})(),
                "ui_controller": type("U", (), {"on_key_press": lambda *_a: False, "input_blocked": False})(),
                "console_controller": type("C", (), {"active": False, "toggle": lambda *_a: None, "process_key": lambda *_a: False})(),
                "input_controller": type("IC", (), {"mouse_x": 100.0, "mouse_y": 200.0})(),
                "screen_to_world": staticmethod(lambda x, y: (float(x), float(y))),
            },
        )()

        def _mark_scene_dirty(self, reason: str) -> None:
            self.scene_dirty = True
            self.scene_dirty_reason = str(reason)
            self.scene_dirty_counter = int(getattr(self, "scene_dirty_counter", 0) or 0) + 1

        window.mark_scene_dirty = _mark_scene_dirty.__get__(window)  # type: ignore[attr-defined]
        window.push_undo_frame = lambda reason: GameWindow.push_undo_frame(window, reason)  # type: ignore[attr-defined]

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

        assert input_capture.handle_key_press(controller, arcade.key.C, arcade.key.MOD_CTRL) is True
        assert capsys.readouterr().out.strip() == "ENTITY_COPY ok count=2"

        assert input_capture.handle_key_press(controller, arcade.key.V, arcade.key.MOD_CTRL) is True
        assert capsys.readouterr().out.strip() == "ENTITY_PASTE ok count=2 primary=b__paste0"

        entities = sc.get_authored_scene_payload()["entities"]
        ids = sorted(e["id"] for e in entities)
        assert "a__paste0" in ids
        assert "b__paste0" in ids

        pasted_primary = next(e for e in entities if e["id"] == "b__paste0")
        assert pasted_primary["x"] == 100.0
        assert pasted_primary["y"] == 200.0

        pasted_a = next(e for e in entities if e["id"] == "a__paste0")
        assert pasted_a["x"] == 91.0
        assert pasted_a["y"] == 182.0

        assert window.entity_select_state.selected_ids == ["a__paste0", "b__paste0"]
        assert window.entity_select_state.primary_id == "b__paste0"
    finally:
        palette.enabled = original_enabled

