from __future__ import annotations


def test_command_palette_macro_asset_runs_and_is_idempotent(capsys) -> None:
    from engine.command_palette import build_default_commands
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
                {"id": "player", "prefab_id": "player", "tags": ["player"], "x": 100.0, "y": 200.0},
            ]
        }
        window.scene_controller = sc

        cmd = next(c for c in build_default_commands(window) if c.id == "macro_asset.core_regions.door_to_upper_hall")

        capsys.readouterr()
        cmd.action(window, None)
        out = capsys.readouterr().out.strip().splitlines()
        assert out and out[-1] == "AUTHOR_MACRO ok action=door_transition created=1 updated=0"
        assert len(window.undo_stack) == 1

        authored = sc.get_authored_scene_payload()
        transition = next(e for e in authored["entities"] if e["id"] == "foo_macro_transition_upper_hall_100_200_0_0")
        assert "SceneTransition" in (transition.get("behaviours") or [])
        assert transition["behaviour_config"]["SceneTransition"]["target_scene"] == "scenes/upper_hall.json"
        assert transition["behaviour_config"]["SceneTransition"]["spawn_id"] == "upper_hall_entry"

        cmd.action(window, None)
        out = capsys.readouterr().out.strip().splitlines()
        assert out and out[-1] == "AUTHOR_MACRO noop reason=no_changes"
        assert len(window.undo_stack) == 1
    finally:
        palette.enabled = original_enabled
