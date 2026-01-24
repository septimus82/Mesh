from __future__ import annotations

import arcade


def test_entity_transform_undo_redo_single_frame(capsys) -> None:
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
                "scene_dirty_counter": 0,
                "scene_dirty_reason": "",
                "scene_dirty": False,
                "undo_stack": [],
                "redo_stack": [],
                "_undo_ts_counter": 0,
                "_undo_suppress_count": 0,
                "entity_snap_to_tile": False,
                "editor_controller": type("E", (), {"active": False})(),
                "ui_controller": type("U", (), {"on_key_press": lambda *_a: False, "input_blocked": False})(),
                "console_controller": type("C", (), {"active": False, "toggle": lambda *_a: None, "process_key": lambda *_a: False})(),
            },
        )()

        def _mark_scene_dirty(self, reason: str) -> None:
            self.scene_dirty = True
            self.scene_dirty_reason = str(reason)
            self.scene_dirty_counter = int(getattr(self, "scene_dirty_counter", 0) or 0) + 1

        window.mark_scene_dirty = _mark_scene_dirty.__get__(window)  # type: ignore[attr-defined]
        window.push_undo_frame = lambda reason: GameWindow.push_undo_frame(window, reason)  # type: ignore[attr-defined]
        window.undo = lambda: GameWindow.undo(window)  # type: ignore[attr-defined]
        window.redo = lambda: GameWindow.redo(window)  # type: ignore[attr-defined]

        sc = SceneController(window)  # type: ignore[arg-type]
        sc.current_scene_path = "scenes/foo.json"
        sc._loaded_scene_source_data = {
            "entities": [
                {"id": "a", "prefab_id": "slime_blob", "x": 0.0, "y": 0.0},
                {"id": "b", "prefab_id": "slime_blob", "x": 2.0, "y": 0.0},
            ]
        }
        window.scene_controller = sc
        window.entity_select_state = EntitySelectState(selected_ids=["a", "b"], primary_id="a")

        controller = type("Ctl", (), {"window": window, "manager": type("M", (), {"press": lambda *_a: None})(), "_keys": set()})()
        capsys.readouterr()

        assert input_capture.handle_key_press(controller, arcade.key.H, arcade.key.MOD_CTRL) is True
        assert capsys.readouterr().out.strip() == "ENTITY_FLIP_X ok count=2"
        assert len(window.undo_stack) == 1
        assert len(window.redo_stack) == 0

        assert input_capture.handle_key_press(controller, arcade.key.Z, arcade.key.MOD_CTRL) is True
        assert capsys.readouterr().out.strip() == "UNDO ok depth=0 redo=1"
        entities = sc.get_authored_scene_payload()["entities"]
        a = next(e for e in entities if e["id"] == "a")
        b = next(e for e in entities if e["id"] == "b")
        assert (a["x"], a["y"]) == (0.0, 0.0)
        assert (b["x"], b["y"]) == (2.0, 0.0)

        assert input_capture.handle_key_press(controller, arcade.key.Y, arcade.key.MOD_CTRL) is True
        assert capsys.readouterr().out.strip() == "REDO ok depth=1 redo=0"
        entities = sc.get_authored_scene_payload()["entities"]
        a = next(e for e in entities if e["id"] == "a")
        b = next(e for e in entities if e["id"] == "b")
        assert (a["x"], a["y"]) == (2.0, 0.0)
        assert (b["x"], b["y"]) == (0.0, 0.0)
    finally:
        palette.enabled = original_enabled
