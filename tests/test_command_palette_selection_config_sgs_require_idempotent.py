from __future__ import annotations

from tests._command_palette_window_stub import CommandPaletteWindowStub, as_game_window


def test_selection_config_sgs_add_require_flag_idempotent_and_skips_player(capsys) -> None:
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
                {"id": "player", "prefab_id": "player", "tags": ["player"], "x": 0.0, "y": 0.0, "behaviours": ["SetGameStateOnEvent"]},
                {
                    "id": "a",
                    "prefab_id": "slime_blob",
                    "x": 1.0,
                    "y": 2.0,
                    "behaviours": ["SetGameStateOnEvent"],
                    "behaviour_config": {"SetGameStateOnEvent": {"require_flags": ["x"]}},
                },
                {"id": "b", "prefab_id": "slime_blob", "x": 3.0, "y": 4.0, "behaviours": ["SetGameStateOnEvent"]},
            ]
        }
        window.scene_controller = sc
        window.entity_select_state = EntitySelectState(selected_ids=["player", "a", "b"], primary_id="a")

        cmd = next(c for c in build_default_commands(window) if c.id == "selection.sgs_add_require_flag")
        capsys.readouterr()
        cmd.action(window, "demo.objective_started")
        assert (
            capsys.readouterr().out.strip()
            == "ENTITY_CONFIG ok action=sgs_add_require_flag changed=2 skipped_player=1 skipped_no_behaviour=0"
        )

        authored = sc.get_authored_scene_payload()
        cfg_a = next(e for e in authored["entities"] if e["id"] == "a")["behaviour_config"]["SetGameStateOnEvent"]
        cfg_b = next(e for e in authored["entities"] if e["id"] == "b")["behaviour_config"]["SetGameStateOnEvent"]
        assert "demo.objective_started" in cfg_a["require_flags"]
        assert "demo.objective_started" in cfg_b["require_flags"]

        # Idempotent re-run.
        cmd.action(window, "demo.objective_started")
        assert capsys.readouterr().out.strip() == "ENTITY_CONFIG noop reason=no_changes"
    finally:
        palette.enabled = original_enabled
