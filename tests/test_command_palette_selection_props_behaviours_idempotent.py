from __future__ import annotations

from tests._command_palette_window_stub import CommandPaletteWindowStub, as_game_window


def test_command_palette_selection_add_remove_behaviour_idempotent(capsys, builtin_behaviours_loaded) -> None:
    from engine.command_palette import build_default_commands
    from engine.entity_select_mode import EntitySelectState
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
                {"id": "a", "prefab_id": "slime_blob", "x": 1.0, "y": 2.0, "behaviours": []},
                {"id": "b", "prefab_id": "slime_blob", "x": 3.0, "y": 4.0, "behaviours": ["Combat"]},
            ]
        }
        window.scene_controller = sc
        window.entity_select_state = EntitySelectState(selected_ids=["a", "b"], primary_id="a")

        add_cmd = next(c for c in build_default_commands(window) if c.id == "selection.add_behaviour")
        remove_cmd = next(c for c in build_default_commands(window) if c.id == "selection.remove_behaviour")

        capsys.readouterr()
        add_cmd.action(window, "Dialogue")
        assert capsys.readouterr().out.strip() == "ENTITY_PROPS ok action=add_behaviour changed=2 skipped_player=0"
        assert len(window.undo_stack) == 1

        # Idempotent second run should not push another undo frame.
        add_cmd.action(window, "Dialogue")
        assert capsys.readouterr().out.strip() == "ENTITY_PROPS noop reason=no_changes"
        assert len(window.undo_stack) == 1

        entities = sc.get_authored_scene_payload()["entities"]
        a = next(e for e in entities if e["id"] == "a")
        b = next(e for e in entities if e["id"] == "b")
        assert "Dialogue" in a.get("behaviours", [])
        assert "Dialogue" in b.get("behaviours", [])

        remove_cmd.action(window, "Dialogue")
        assert capsys.readouterr().out.strip() == "ENTITY_PROPS ok action=remove_behaviour changed=2 skipped_player=0"

        # Idempotent removal.
        remove_cmd.action(window, "Dialogue")
        assert capsys.readouterr().out.strip() == "ENTITY_PROPS noop reason=no_changes"
    finally:
        palette.enabled = original_enabled
