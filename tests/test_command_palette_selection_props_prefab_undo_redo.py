from __future__ import annotations

from tests._command_palette_window_stub import CommandPaletteWindowStub, as_game_window


def test_command_palette_selection_set_prefab_multi_skips_player_and_undo_redo(capsys) -> None:
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
                {"id": "player", "prefab_id": "player", "tags": ["player"], "x": 0.0, "y": 0.0},
                {"id": "a", "prefab_id": "slime_blob", "x": 1.0, "y": 2.0},
                {"id": "b", "prefab_id": "slime_blob", "x": 3.0, "y": 4.0},
            ]
        }
        window.scene_controller = sc
        window.entity_select_state = EntitySelectState(selected_ids=["player", "a", "b"], primary_id="player")

        cmd = next(c for c in build_default_commands(window) if c.id == "selection.set_prefab_id")
        assert cmd.prompt is not None and cmd.prompt.kind == "pick"

        capsys.readouterr()
        cmd.action(window, "rat_scurrier")
        assert capsys.readouterr().out.strip() == "ENTITY_PROPS ok action=set_prefab_id changed=2 skipped_player=1"
        assert len(window.undo_stack) == 1

        entities = sc.get_authored_scene_payload()["entities"]
        assert next(e for e in entities if e["id"] == "a")["prefab_id"] == "rat_scurrier"
        assert next(e for e in entities if e["id"] == "b")["prefab_id"] == "rat_scurrier"
        assert next(e for e in entities if e["id"] == "player")["prefab_id"] == "player"

        capsys.readouterr()
        window.undo()
        capsys.readouterr()
        entities = sc.get_authored_scene_payload()["entities"]
        assert next(e for e in entities if e["id"] == "a")["prefab_id"] == "slime_blob"
        assert next(e for e in entities if e["id"] == "b")["prefab_id"] == "slime_blob"

        window.redo()
        capsys.readouterr()
        entities = sc.get_authored_scene_payload()["entities"]
        assert next(e for e in entities if e["id"] == "a")["prefab_id"] == "rat_scurrier"
        assert next(e for e in entities if e["id"] == "b")["prefab_id"] == "rat_scurrier"
    finally:
        palette.enabled = original_enabled
