from __future__ import annotations

import engine.optional_arcade as optional_arcade


def test_selection_config_tz_set_radius_mutates_only_triggerzone_and_undo_redo(capsys) -> None:
    from engine.command_palette import build_default_commands
    from engine.entity_select_mode import EntitySelectState
    from engine.game import GameWindow
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
                "ui_controller": type("U", (), {"on_key_press": lambda *_a: False, "input_blocked": False})(),
                "console_controller": type("C", (), {"active": False, "toggle": lambda *_a: None, "process_key": lambda *_a: False})(),
                "editor_controller": type("E", (), {"active": False})(),
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
                {"id": "player", "prefab_id": "player", "tags": ["player"], "x": 0.0, "y": 0.0},
                {"id": "tz", "prefab_id": "slime_blob", "x": 1.0, "y": 2.0, "behaviours": ["TriggerZone"]},
                {"id": "other", "prefab_id": "slime_blob", "x": 3.0, "y": 4.0, "behaviours": []},
            ]
        }
        window.scene_controller = sc
        window.entity_select_state = EntitySelectState(selected_ids=["player", "tz", "other"], primary_id="tz")

        cmd = next(c for c in build_default_commands(window) if c.id == "selection.tz_set_radius")

        capsys.readouterr()
        cmd.action(window, "48")
        assert (
            capsys.readouterr().out.strip()
            == "ENTITY_CONFIG ok action=tz_set_radius changed=1 skipped_player=1 skipped_no_behaviour=1"
        )
        assert len(window.undo_stack) == 1

        authored = sc.get_authored_scene_payload()
        tz_ent = next(e for e in authored["entities"] if e["id"] == "tz")
        assert tz_ent["behaviour_config"]["TriggerZone"]["trigger_radius"] == 48.0

        # Idempotent re-run.
        cmd.action(window, "48")
        assert capsys.readouterr().out.strip() == "ENTITY_CONFIG noop reason=no_changes"
        assert len(window.undo_stack) == 1

        window.undo()
        capsys.readouterr()
        authored = sc.get_authored_scene_payload()
        tz_ent = next(e for e in authored["entities"] if e["id"] == "tz")
        root = tz_ent.get("behaviour_config") if isinstance(tz_ent.get("behaviour_config"), dict) else {}
        cfg = root.get("TriggerZone") if isinstance(root, dict) and isinstance(root.get("TriggerZone"), dict) else {}
        assert cfg.get("trigger_radius", 0.0) in (0.0, None)

        window.redo()
        capsys.readouterr()
        authored = sc.get_authored_scene_payload()
        tz_ent = next(e for e in authored["entities"] if e["id"] == "tz")
        assert tz_ent["behaviour_config"]["TriggerZone"]["trigger_radius"] == 48.0
    finally:
        palette.enabled = original_enabled

