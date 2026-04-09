from __future__ import annotations

from tests._command_palette_window_stub import CommandPaletteWindowStub, as_game_window


def test_command_palette_macro_asset_runs_and_is_idempotent(capsys) -> None:
    from engine.command_palette import build_default_commands
    from engine.palette_mode import get_state
    from engine.scene_controller import SceneController

    palette = get_state()
    original_enabled = bool(palette.enabled)
    palette.enabled = False
    try:
        window = CommandPaletteWindowStub()
        sc = SceneController(as_game_window(window))
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
