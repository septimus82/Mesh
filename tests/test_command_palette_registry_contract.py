"""Contract tests for the command palette registry refactor.

These tests verify that the refactored command palette maintains
identical behavior to the original implementation.
"""
from __future__ import annotations


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
