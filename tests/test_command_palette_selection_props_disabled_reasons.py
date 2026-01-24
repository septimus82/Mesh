from __future__ import annotations


def test_command_palette_selection_props_disabled_reasons_stable() -> None:
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
        "selection.set_prefab_id",
        "selection.add_behaviour",
        "selection.remove_behaviour",
        "selection.set_name",
        "selection.set_tag",
    ):
        enabled, reason = cmds[cid].is_enabled(window)
        assert enabled is False
        assert reason == "no_selection"

    window.entity_select_state = EntitySelectState(selected_ids=["player"], primary_id="player")
    cmds = {c.id: c for c in build_default_commands(window)}
    for cid in (
        "selection.set_prefab_id",
        "selection.add_behaviour",
        "selection.remove_behaviour",
        "selection.set_name",
        "selection.set_tag",
    ):
        enabled, reason = cmds[cid].is_enabled(window)
        assert enabled is False
        assert reason == "only_player"

    window = type("W", (), {"scene_controller": None, "entity_select_state": EntitySelectState(selected_ids=["a"], primary_id="a")})()
    cmds = {c.id: c for c in build_default_commands(window)}
    enabled, reason = cmds["selection.set_tag"].is_enabled(window)
    assert enabled is False
    assert reason == "no_authored_payload"

