from __future__ import annotations

from tests._command_palette_window_stub import CommandPaletteWindowStub, as_game_window


def test_selection_config_scene_transition_target_scene_pick_prompt(monkeypatch, capsys) -> None:
    from engine.command_palette import build_default_commands
    from engine.entity_select_mode import EntitySelectState
    from engine.palette_mode import get_state
    from engine.scene_controller import SceneController

    palette = get_state()
    original_enabled = bool(palette.enabled)
    palette.enabled = False
    try:
        monkeypatch.setattr("engine.scene_index.iter_known_scene_paths", lambda: ["scenes/a.json", "scenes/b.json"])

        window = CommandPaletteWindowStub()
        sc = SceneController(as_game_window(window))
        sc.current_scene_path = "scenes/foo.json"
        sc._loaded_scene_source_data = {
            "entities": [
                {"id": "t", "prefab_id": "slime_blob", "x": 1.0, "y": 2.0, "behaviours": ["SceneTransition"]},
                {"id": "x", "prefab_id": "slime_blob", "x": 3.0, "y": 4.0, "behaviours": []},
            ]
        }
        window.scene_controller = sc
        window.entity_select_state = EntitySelectState(selected_ids=["t", "x"], primary_id="t")

        cmd = next(c for c in build_default_commands(window) if c.id == "selection.st_set_target_scene")
        assert cmd.prompt is not None and cmd.prompt.kind == "pick"
        assert cmd.prompt.options_provider is not None
        assert cmd.prompt.options_provider(window) == [("scenes/a.json", "scenes/a.json"), ("scenes/b.json", "scenes/b.json")]

        capsys.readouterr()
        cmd.action(window, "scenes/b.json")
        assert (
            capsys.readouterr().out.strip()
            == "ENTITY_CONFIG ok action=st_set_target_scene changed=1 skipped_player=0 skipped_no_behaviour=1"
        )
        authored = sc.get_authored_scene_payload()
        cfg = next(e for e in authored["entities"] if e["id"] == "t")["behaviour_config"]["SceneTransition"]
        assert cfg["target_scene"] == "scenes/b.json"
    finally:
        palette.enabled = original_enabled
