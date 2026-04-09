"""Contract tests for the command palette registry refactor.

These tests verify that the refactored command palette maintains
identical behavior to the original implementation.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest


class TestCommandPaletteRegistryContract:
    """Contract tests ensuring the registry-based implementation is correct."""

    def test_default_commands_are_deterministic(self) -> None:
        """Calling build_default_commands twice yields identical ID lists."""
        from engine.command_palette import build_default_commands

        window = object()
        first = [c.id for c in build_default_commands(window)]
        second = [c.id for c in build_default_commands(window)]
        assert first == second, "Commands must be deterministic across calls"

    def test_no_duplicate_command_ids(self) -> None:
        """All command IDs must be unique."""
        from engine.command_palette import build_default_commands

        window = object()
        ids = [c.id for c in build_default_commands(window)]
        assert len(ids) == len(set(ids)), f"Duplicate IDs found: {[i for i in ids if ids.count(i) > 1]}"

    def test_all_commands_have_required_fields(self) -> None:
        """Every CommandSpec must have non-empty id, title, section."""
        from engine.command_palette import build_default_commands

        window = object()
        for cmd in build_default_commands(window):
            assert cmd.id, f"Command missing id: {cmd}"
            assert cmd.title, f"Command missing title: {cmd.id}"
            assert cmd.section, f"Command missing section: {cmd.id}"

    def test_command_actions_are_callable(self) -> None:
        """Every command action must be callable."""
        from engine.command_palette import build_default_commands

        window = object()
        for cmd in build_default_commands(window):
            assert callable(cmd.action), f"Command {cmd.id} action is not callable"

    def test_command_is_enabled_are_callable(self) -> None:
        """Every command is_enabled must be callable."""
        from engine.command_palette import build_default_commands

        window = object()
        for cmd in build_default_commands(window):
            assert callable(cmd.is_enabled), f"Command {cmd.id} is_enabled is not callable"

    def test_prompt_default_value_fn_callable(self) -> None:
        """Prompt default_value_fn must be callable."""
        from engine.command_palette import build_default_commands

        window = object()
        for cmd in build_default_commands(window):
            if cmd.prompt:
                assert callable(cmd.prompt.default_value_fn), f"Command {cmd.id} prompt.default_value_fn not callable"
            if cmd.prompts:
                for i, p in enumerate(cmd.prompts):
                    assert callable(p.default_value_fn), f"Command {cmd.id} prompts[{i}].default_value_fn not callable"

    def test_base_command_order_stable(self) -> None:
        """Base command IDs must be in the expected order."""
        from engine.command_palette import build_default_commands

        window = object()
        ids = [c.id for c in build_default_commands(window)]

        expected_base = [
            "mode.tile_paint.toggle",
            "mode.entity_paint.toggle",
            "mode.palette.toggle",
            "mode.capture.toggle",
            "view.ghost_originals.toggle",
            "palette.clear_recent",
            "palette.reset_ui_layout",
            "scene.reload",
            "scene.goto",
            "scene.recent",
            "scene.persist_arm.toggle",
            "scene.persist",
            "scene.save_as",
            "scene.create",
            "planes.add",
            "planes.duplicate",
            "planes.remove",
            "planes.move_up",
            "planes.move_down",
            "planes.move_top",
            "planes.move_bottom",
            "planes.move_to",
            "planes.toggle_repeat",
            "planes.toggle_repeat_x",
            "planes.toggle_repeat_y",
            "planes.select",
            "planes.select_prev",
            "planes.select_next",
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

        # Verify base commands match exactly (ignoring macro_asset.* commands)
        actual_base = [i for i in ids if not i.startswith("macro_asset.")]
        assert actual_base == expected_base, f"Base command order mismatch:\nExpected: {expected_base}\nActual: {actual_base}"

    def test_macro_asset_commands_sorted(self) -> None:
        """Macro asset commands must be sorted by (pack_id, id)."""
        from engine.command_palette import build_default_commands

        window = object()
        ids = [c.id for c in build_default_commands(window)]

        # Extract macro_asset commands
        macro_ids = [i for i in ids if i.startswith("macro_asset.")]
        assert macro_ids == sorted(macro_ids), "Macro asset commands must be sorted"

    def test_keywords_are_tuples(self) -> None:
        """Command keywords must be tuples of strings."""
        from engine.command_palette import build_default_commands

        window = object()
        for cmd in build_default_commands(window):
            assert isinstance(cmd.keywords, tuple), f"Command {cmd.id} keywords is not a tuple"
            for kw in cmd.keywords:
                assert isinstance(kw, str), f"Command {cmd.id} keyword {kw!r} is not a string"

    @pytest.mark.fast
    def test_action_handler_symbols_exported_for_monkeypatch(self) -> None:
        """Registry must keep stable action handler symbols for monkeypatch targets."""
        import engine.command_palette_registry as registry

        expected_handlers = [
            "action_toggle_tile_paint",
            "action_toggle_entity_paint",
            "action_toggle_palette_mode",
            "action_toggle_capture",
            "action_toggle_ghost_originals",
            "action_palette_clear_recent",
            "action_palette_reset_ui_layout",
            "action_scene_reload",
            "action_scene_toggle_persist_armed",
            "action_scene_persist",
            "action_scene_save_as",
            "action_scene_create",
            "action_go_to_scene",
            "action_recent_scene",
            "action_planes_add",
            "action_planes_duplicate",
            "action_planes_remove",
            "action_planes_move_up",
            "action_planes_move_down",
            "action_planes_move_top",
            "action_planes_move_bottom",
            "action_planes_move_to",
            "action_planes_toggle_repeat",
            "action_planes_toggle_repeat_x",
            "action_planes_toggle_repeat_y",
            "action_planes_select",
            "action_planes_select_prev",
            "action_planes_select_next",
            "action_props_set_prefab_id",
            "action_props_add_behaviour",
            "action_props_remove_behaviour",
            "action_props_set_name",
            "action_props_add_tag",
            "action_props_remove_tag",
            "action_props_toggle_tag",
            "action_batch_rename",
            "action_set_names",
            "action_align_selection",
            "action_distribute_selection",
            "action_snap_to_grid",
            "action_nudge_selection",
            "action_rotate_selection",
            "action_mirror_selection",
            "action_group_selection",
            "action_ungroup_selection",
            "action_duplicate_to_grid",
            "action_duplicate_along_path",
            "action_scatter_selection",
            "action_config_tz_set_zone_id",
            "action_config_tz_set_radius",
            "action_config_sgs_set_toast",
            "action_config_sgs_add_require_flag",
            "action_config_sgs_add_forbid_flag",
            "action_config_sgs_set_flag_true",
            "action_config_st_set_target_scene",
            "action_config_st_set_spawn_id",
            "action_macro_objective_zone",
            "action_macro_door_transition",
            "action_macro_dialogue_choice_flag",
        ]

        for name in expected_handlers:
            fn = getattr(registry, name, None)
            assert callable(fn), f"Missing/uncallable handler symbol: {name}"

    @pytest.mark.fast
    def test_support_helper_symbols_preserve_registry_surface(self) -> None:
        import engine.command_palette_registry as registry
        import engine.command_palette_registry_options as options
        import engine.command_palette_registry_parse_helpers as parse_helpers
        import engine.command_palette_registry_selection as selection
        import engine.command_palette_registry_support as support

        for name in (
            "enabled_has_scene",
            "enabled_selection_has_non_player",
            "default_scene_create",
            "_set_last_props_action",
            "_set_last_config_action",
            "_get_player_pos_from_authored",
            "_get_entity_pos_from_authored",
            "_get_cursor_world_pos",
            "_resolve_macro_anchor_pos",
        ):
            assert getattr(registry, name, None) is getattr(support, name, None), f"registry helper drifted: {name}"

        for name in (
            "_list_prefab_ids_from_assets_cached",
            "_list_behaviour_names_cached",
            "options_all_scenes",
            "options_recent_scenes",
            "options_prefab_ids",
            "options_behaviour_names",
            "options_behaviours_in_selection",
            "options_scene_paths",
            "options_dialogue_speakers",
            "options_macro_anchor",
        ):
            assert getattr(registry, name, None) is getattr(options, name, None), f"registry option helper drifted: {name}"

        for name in (
            "_entity_has_behaviour",
            "_get_authored_payload",
            "_get_selection_ids_and_primary",
            "_parse_float",
        ):
            assert getattr(registry, name, None) is getattr(selection, name.removeprefix("_"), None), (
                f"registry selection helper drifted: {name}"
            )

        for name in (
            "_parse_toast_and_seconds",
            "_parse_align_args",
            "_parse_distribute_args",
            "_parse_snap_args",
            "_parse_nudge_args",
            "_parse_rotate_args",
            "_parse_planes_toggle_repeat_args",
            "_parse_planes_select_args",
            "_parse_planes_move_to_args",
        ):
            assert getattr(registry, name, None) is getattr(
                parse_helpers, name, None
            ), f"registry parse helper drifted: {name}"

    @pytest.mark.fast
    def test_support_module_stays_focused_on_enablement_defaults_and_macro_helpers(self) -> None:
        source_path = Path("engine/command_palette_registry_support.py")
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))

        imported_modules: set[str] = set()
        top_level_defs: list[str] = []
        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_modules.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imported_modules.add(module)
            elif isinstance(node, ast.FunctionDef):
                top_level_defs.append(node.name)

        forbidden_import_prefixes = (
            "mesh_cli",
            "engine.command_palette_registry_actions",
            "engine.command_palette_registry_defs",
            "engine.command_palette_registry_options",
        )
        for module_name in sorted(imported_modules):
            assert not module_name.startswith(
                forbidden_import_prefixes
            ), f"support module import drifted: {module_name}"

        allowed_prefixes = ("enabled_", "default_", "_set_last_", "_get_", "_resolve_", "_log_swallow")
        unexpected_defs = [name for name in top_level_defs if not name.startswith(allowed_prefixes)]
        assert unexpected_defs == [], f"support module became a junk drawer: {unexpected_defs}"

    @pytest.mark.fast
    def test_known_command_ids_present_and_count_stable(self) -> None:
        """Command IDs and overall default command count remain stable."""
        from engine.command_palette import build_default_commands

        ids = [c.id for c in build_default_commands(object())]
        known_ids = {
            "mode.tile_paint.toggle",
            "palette.clear_recent",
            "palette.reset_ui_layout",
            "scene.reload",
            "planes.add",
            "selection.add_behaviour",
            "selection.scatter",
            "macro.objective_zone",
            "macro.door_transition",
            "macro.dialogue_choice_flag",
        }
        assert known_ids.issubset(set(ids))
        assert len(ids) == 65


class TestFilterCommands:
    """Tests for the filter_commands function."""

    def test_empty_query_returns_all(self) -> None:
        """An empty query returns all commands."""
        from engine.command_palette import build_default_commands, filter_commands

        window = object()
        cmds = build_default_commands(window)
        result = filter_commands(cmds, "")
        assert len(result) == len(cmds)

    def test_query_filters_by_title(self) -> None:
        """Query matches on title."""
        from engine.command_palette import build_default_commands, filter_commands

        window = object()
        cmds = build_default_commands(window)
        result = filter_commands(cmds, "tile")
        assert any(c.id == "mode.tile_paint.toggle" for c in result)

    def test_query_filters_by_keyword(self) -> None:
        """Query matches on keywords."""
        from engine.command_palette import build_default_commands, filter_commands

        window = object()
        cmds = build_default_commands(window)
        result = filter_commands(cmds, "f11")
        assert any(c.id == "mode.tile_paint.toggle" for c in result)

    def test_exact_title_match_ranks_first(self) -> None:
        """Exact title prefix matches rank first."""
        from engine.command_palette import build_default_commands, filter_commands

        window = object()
        cmds = build_default_commands(window)
        result = filter_commands(cmds, "toggle tile")
        # "Toggle Tile Paint" should be first (starts with "Toggle")
        assert result[0].id == "mode.tile_paint.toggle"


class TestFilterOptions:
    """Tests for the filter_options function."""

    def test_empty_query_returns_all(self) -> None:
        """An empty query returns all options."""
        from engine.command_palette import filter_options

        options = [("a", "Apple"), ("b", "Banana"), ("c", "Cherry")]
        result = filter_options(options, "")
        assert len(result) == 3

    def test_query_filters_by_label(self) -> None:
        """Query matches on label."""
        from engine.command_palette import filter_options

        options = [("a", "Apple"), ("b", "Banana"), ("c", "Cherry")]
        result = filter_options(options, "ban")
        assert len(result) == 1
        assert result[0][0] == "b"

    def test_query_filters_by_value(self) -> None:
        """Query matches on value."""
        from engine.command_palette import filter_options

        options = [("apple", "Fruit A"), ("banana", "Fruit B")]
        result = filter_options(options, "apple")
        assert len(result) == 1
        assert result[0][1] == "Fruit A"
