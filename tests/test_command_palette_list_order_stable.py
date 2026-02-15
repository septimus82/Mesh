from __future__ import annotations


def test_command_palette_list_order_stable() -> None:
    from engine.command_palette import build_default_commands
    from engine.tooling_runtime.macro_assets import list_macros

    window = object()
    ids = [c.id for c in build_default_commands(window)]
    base = [
        "mode.tile_paint.toggle",
        "mode.entity_paint.toggle",
        "mode.palette.toggle",
        "mode.capture.toggle",
        "view.ghost_originals.toggle",
        "scene.reload",
        "scene.goto",
        "scene.recent",
        "scene.persist_arm.toggle",
        "scene.persist",
        "scene.save_as",
        "scene.create",
        "selection.set_prefab_id",
        "selection.add_behaviour",
        "selection.remove_behaviour",
        "selection.set_name",
        "selection.set_tag",
        "selection.remove_tag",
        "selection.toggle_tag",
        "selection.batch_rename",
        "selection.set_names",
        "selection.align",
        "selection.distribute",
        "selection.snap_to_grid",
        "selection.nudge",
        "selection.rotate",
        "selection.mirror",
        "selection.group",
        "selection.ungroup",
        "selection.duplicate_to_grid",
        "selection.duplicate_along_path",
        "selection.scatter",
        "selection.tz_set_zone_id",
        "selection.tz_set_radius",
        "selection.sgs_set_toast",
        "selection.sgs_add_require_flag",
        "selection.sgs_add_forbid_flag",
        "selection.sgs_set_flag_true",
        "selection.st_set_target_scene",
        "selection.st_set_spawn_id",
        "macro.objective_zone",
        "macro.door_transition",
        "macro.dialogue_choice_flag",
    ]
    macro_asset_ids = [f"macro_asset.{s.pack_id}.{s.id}" for s in list_macros()]
    assert ids == base + macro_asset_ids
