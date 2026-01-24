from __future__ import annotations


def test_selection_config_disabled_reasons_stable() -> None:
    from engine.command_palette import build_default_commands
    from engine.entity_select_mode import EntitySelectState

    class _SC:
        current_scene_path = "scenes/foo.json"

        @staticmethod
        def get_authored_scene_payload() -> dict:
            return {"entities": [{"id": "player", "prefab_id": "player", "tags": ["player"]}]}

    window = type("W", (), {"scene_controller": _SC(), "entity_select_state": EntitySelectState(selected_ids=[], primary_id=None)})()
    cmds = {c.id: c for c in build_default_commands(window)}

    for cid in (
        "selection.tz_set_zone_id",
        "selection.tz_set_radius",
        "selection.sgs_set_toast",
        "selection.sgs_add_require_flag",
        "selection.sgs_add_forbid_flag",
        "selection.sgs_set_flag_true",
        "selection.st_set_target_scene",
        "selection.st_set_spawn_id",
    ):
        enabled, reason = cmds[cid].is_enabled(window)
        assert enabled is False
        assert reason == "no_selection"

    window.entity_select_state = EntitySelectState(selected_ids=["player"], primary_id="player")
    cmds = {c.id: c for c in build_default_commands(window)}
    for cid in (
        "selection.tz_set_zone_id",
        "selection.tz_set_radius",
        "selection.sgs_set_toast",
        "selection.sgs_add_require_flag",
        "selection.sgs_add_forbid_flag",
        "selection.sgs_set_flag_true",
        "selection.st_set_target_scene",
        "selection.st_set_spawn_id",
    ):
        enabled, reason = cmds[cid].is_enabled(window)
        assert enabled is False
        assert reason == "only_player"

    window = type("W", (), {"scene_controller": None, "entity_select_state": EntitySelectState(selected_ids=["a"], primary_id="a")})()
    cmds = {c.id: c for c in build_default_commands(window)}
    enabled, reason = cmds["selection.tz_set_radius"].is_enabled(window)
    assert enabled is False
    assert reason == "no_authored_payload"

