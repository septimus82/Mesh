from __future__ import annotations

from tests._command_palette_window_stub import CommandPaletteWindowStub, as_game_window


def test_command_palette_selection_set_name_affects_primary_only(capsys) -> None:
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
                {"id": "a", "prefab_id": "slime_blob", "x": 1.0, "y": 2.0, "name": "A"},
                {"id": "b", "prefab_id": "slime_blob", "x": 3.0, "y": 4.0, "name": "B"},
            ]
        }
        window.scene_controller = sc
        window.entity_select_state = EntitySelectState(selected_ids=["a", "b"], primary_id="b")

        cmd = next(c for c in build_default_commands(window) if c.id == "selection.set_name")
        capsys.readouterr()
        cmd.action(window, "Hello")
        assert capsys.readouterr().out.strip() == "ENTITY_PROPS ok action=set_name changed=1 skipped_player=0"

        entities = sc.get_authored_scene_payload()["entities"]
        assert next(e for e in entities if e["id"] == "a")["name"] == "A"
        assert next(e for e in entities if e["id"] == "b")["name"] == "Hello"
    finally:
        palette.enabled = original_enabled
