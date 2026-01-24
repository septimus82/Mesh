"""Contract tests for editor multiselect and group transform operations.

These tests verify the multi-selection and group transform operations work
correctly without any arcade/pygame dependencies (pure unit tests).
"""

from __future__ import annotations

import copy
import pytest

from engine.editor.editor_multiselect_ops import (
    clear_selection,
    get_primary_id,
    is_entity_selected,
    select_single,
    toggle_selection,
)
from engine.editor.editor_transform_ops import (
    MoveEntityCommand,
    MoveEntitiesCommand,
    apply_group_move_command,
    apply_snap_to_xy,
    create_group_move_command_from_drag,
    invert_group_move_command,
)


# ------------------------------------------------------------------------------
# Multiselect ops tests
# ------------------------------------------------------------------------------


class TestToggleSelection:
    """Tests for toggle_selection helper."""

    def test_no_shift_replaces_selection(self) -> None:
        """Without shift, clicking replaces entire selection."""
        current = ["a", "b", "c"]
        result = toggle_selection(current, "d", shift=False)
        assert result == ["d"]

    def test_shift_adds_to_selection(self) -> None:
        """With shift, clicking unselected entity adds it."""
        current = ["a", "b"]
        result = toggle_selection(current, "c", shift=True)
        assert result == ["a", "b", "c"]

    def test_shift_removes_from_selection(self) -> None:
        """With shift, clicking selected entity removes it."""
        current = ["a", "b", "c"]
        result = toggle_selection(current, "b", shift=True)
        assert result == ["a", "c"]

    def test_does_not_mutate_input(self) -> None:
        """Input list should not be mutated."""
        original = ["a", "b"]
        copy_original = list(original)
        toggle_selection(original, "c", shift=True)
        assert original == copy_original

    def test_deterministic_ordering(self) -> None:
        """Selection maintains insertion order (deterministic)."""
        result = []
        result = toggle_selection(result, "c", shift=True)
        result = toggle_selection(result, "a", shift=True)
        result = toggle_selection(result, "b", shift=True)
        assert result == ["c", "a", "b"]

    def test_empty_clicked_id_returns_unchanged(self) -> None:
        """Empty clicked_id returns current selection unchanged."""
        current = ["a", "b"]
        result = toggle_selection(current, "", shift=True)
        assert result == ["a", "b"]


class TestSelectSingle:
    """Tests for select_single helper."""

    def test_returns_single_item_list(self) -> None:
        """Returns list with just the clicked ID."""
        result = select_single("hero")
        assert result == ["hero"]

    def test_empty_returns_empty(self) -> None:
        """Empty ID returns empty list."""
        result = select_single("")
        assert result == []


class TestGetPrimaryId:
    """Tests for get_primary_id helper."""

    def test_clicked_in_selection_becomes_primary(self) -> None:
        """If clicked entity is in selection, it becomes primary."""
        selected = ["a", "b", "c"]
        result = get_primary_id(selected, "b")
        assert result == "b"

    def test_clicked_not_in_selection_returns_first(self) -> None:
        """If clicked entity not in selection, returns first."""
        selected = ["a", "b", "c"]
        result = get_primary_id(selected, "d")
        assert result == "a"

    def test_empty_selection_returns_none(self) -> None:
        """Empty selection returns None."""
        result = get_primary_id([], "hero")
        assert result is None


class TestIsEntitySelected:
    """Tests for is_entity_selected helper."""

    def test_returns_true_for_selected(self) -> None:
        """Returns True when entity is in selection."""
        assert is_entity_selected(["a", "b", "c"], "b") is True

    def test_returns_false_for_not_selected(self) -> None:
        """Returns False when entity is not in selection."""
        assert is_entity_selected(["a", "b", "c"], "d") is False


class TestClearSelection:
    """Tests for clear_selection helper."""

    def test_returns_empty_list(self) -> None:
        """Returns empty list."""
        assert clear_selection() == []


# ------------------------------------------------------------------------------
# MoveEntitiesCommand tests
# ------------------------------------------------------------------------------


class TestMoveEntitiesCommand:
    """Tests for MoveEntitiesCommand dataclass."""

    def test_to_dict_structure(self) -> None:
        """to_dict returns correct structure with type and moves array."""
        cmd = MoveEntitiesCommand(
            moves=(
                MoveEntityCommand(entity_id="hero", start_xy=(100.0, 200.0), end_xy=(150.0, 250.0)),
                MoveEntityCommand(entity_id="npc", start_xy=(300.0, 400.0), end_xy=(350.0, 450.0)),
            )
        )
        result = cmd.to_dict()

        assert result["type"] == "MoveEntities"
        assert len(result["moves"]) == 2
        assert result["moves"][0]["entity_name"] == "hero"
        assert result["moves"][1]["entity_name"] == "npc"

    def test_from_dict_roundtrip(self) -> None:
        """from_dict correctly reconstructs a command from its dict form."""
        original = MoveEntitiesCommand(
            moves=(
                MoveEntityCommand(entity_id="hero", start_xy=(100.0, 200.0), end_xy=(150.0, 250.0)),
                MoveEntityCommand(entity_id="npc", start_xy=(300.0, 400.0), end_xy=(350.0, 450.0)),
            )
        )
        serialized = original.to_dict()
        restored = MoveEntitiesCommand.from_dict(serialized)

        assert len(restored.moves) == len(original.moves)
        for orig, rest in zip(original.moves, restored.moves):
            assert rest.entity_id == orig.entity_id
            assert rest.start_xy == orig.start_xy
            assert rest.end_xy == orig.end_xy


# ------------------------------------------------------------------------------
# apply_group_move_command tests
# ------------------------------------------------------------------------------


class TestApplyGroupMoveCommand:
    """Tests for apply_group_move_command helper."""

    @pytest.fixture()
    def sample_scene(self) -> dict:
        """Minimal scene with multiple entities."""
        return {
            "entities": [
                {"name": "hero", "x": 100, "y": 200, "sprite": "hero.png"},
                {"name": "npc_1", "x": 300, "y": 400, "sprite": "npc.png"},
                {"name": "chest", "x": 500, "y": 600, "sprite": "chest.png"},
            ]
        }

    def test_moves_all_specified_entities(self, sample_scene: dict) -> None:
        """All entities in the command are moved."""
        cmd = MoveEntitiesCommand(
            moves=(
                MoveEntityCommand(entity_id="hero", start_xy=(100.0, 200.0), end_xy=(116.0, 216.0)),
                MoveEntityCommand(entity_id="npc_1", start_xy=(300.0, 400.0), end_xy=(316.0, 416.0)),
            )
        )

        result = apply_group_move_command(sample_scene, cmd)

        assert result["entities"][0]["x"] == 116.0
        assert result["entities"][0]["y"] == 216.0
        assert result["entities"][1]["x"] == 316.0
        assert result["entities"][1]["y"] == 416.0
        # Chest unchanged
        assert result["entities"][2]["x"] == 500
        assert result["entities"][2]["y"] == 600

    def test_does_not_mutate_original(self, sample_scene: dict) -> None:
        """apply_group_move_command creates a deep copy."""
        original = copy.deepcopy(sample_scene)
        cmd = MoveEntitiesCommand(
            moves=(MoveEntityCommand(entity_id="hero", start_xy=(100.0, 200.0), end_xy=(999.0, 999.0)),)
        )

        apply_group_move_command(sample_scene, cmd)

        assert sample_scene == original


# ------------------------------------------------------------------------------
# invert_group_move_command tests
# ------------------------------------------------------------------------------


class TestInvertGroupMoveCommand:
    """Tests for invert_group_move_command helper."""

    def test_swaps_all_start_and_end(self) -> None:
        """All moves in command have start/end swapped."""
        cmd = MoveEntitiesCommand(
            moves=(
                MoveEntityCommand(entity_id="hero", start_xy=(100.0, 200.0), end_xy=(150.0, 250.0)),
                MoveEntityCommand(entity_id="npc", start_xy=(300.0, 400.0), end_xy=(350.0, 450.0)),
            )
        )

        inverted = invert_group_move_command(cmd)

        assert inverted.moves[0].start_xy == (150.0, 250.0)
        assert inverted.moves[0].end_xy == (100.0, 200.0)
        assert inverted.moves[1].start_xy == (350.0, 450.0)
        assert inverted.moves[1].end_xy == (300.0, 400.0)

    def test_double_invert_returns_original(self) -> None:
        """Inverting twice returns the original values."""
        original = MoveEntitiesCommand(
            moves=(
                MoveEntityCommand(entity_id="hero", start_xy=(100.0, 200.0), end_xy=(150.0, 250.0)),
                MoveEntityCommand(entity_id="npc", start_xy=(300.0, 400.0), end_xy=(350.0, 450.0)),
            )
        )

        double_inverted = invert_group_move_command(invert_group_move_command(original))

        for orig, restored in zip(original.moves, double_inverted.moves):
            assert restored.entity_id == orig.entity_id
            assert restored.start_xy == orig.start_xy
            assert restored.end_xy == orig.end_xy


# ------------------------------------------------------------------------------
# create_group_move_command_from_drag tests
# ------------------------------------------------------------------------------


class TestCreateGroupMoveCommandFromDrag:
    """Tests for create_group_move_command_from_drag helper."""

    def test_returns_none_for_zero_delta(self) -> None:
        """Returns None if delta is zero."""
        entity_starts = [("hero", (100.0, 200.0)), ("npc", (300.0, 400.0))]
        result = create_group_move_command_from_drag(entity_starts, (0.0, 0.0))
        assert result is None

    def test_returns_none_for_empty_entities(self) -> None:
        """Returns None if no entities provided."""
        result = create_group_move_command_from_drag([], (10.0, 10.0))
        assert result is None

    def test_applies_same_delta_to_all(self) -> None:
        """All entities have same delta applied."""
        entity_starts = [
            ("hero", (100.0, 200.0)),
            ("npc", (300.0, 400.0)),
            ("chest", (500.0, 600.0)),
        ]
        delta = (16.0, 32.0)

        result = create_group_move_command_from_drag(entity_starts, delta)

        assert result is not None
        assert len(result.moves) == 3
        # Verify each entity moved by exactly delta
        for move, (eid, start) in zip(result.moves, entity_starts):
            assert move.entity_id == eid
            assert move.start_xy == start
            assert move.end_xy == (start[0] + delta[0], start[1] + delta[1])

    def test_preserves_entity_order(self) -> None:
        """Entity order in command matches input order (deterministic)."""
        entity_starts = [("c", (300.0, 300.0)), ("a", (100.0, 100.0)), ("b", (200.0, 200.0))]
        result = create_group_move_command_from_drag(entity_starts, (10.0, 10.0))

        assert result is not None
        assert [m.entity_id for m in result.moves] == ["c", "a", "b"]


# ------------------------------------------------------------------------------
# Snapping anchor behavior tests
# ------------------------------------------------------------------------------


class TestSnappingAnchorBehavior:
    """Tests verifying snapping is only applied to primary/anchor entity."""

    def test_snap_delta_applied_uniformly(self) -> None:
        """
        When primary snaps, delta is computed from snapped position.
        All other entities move by the same delta, not individually snapped.
        """
        # Primary at (100, 100), dragged to (107, 107) -> snaps to (112, 112) with grid16
        # Delta = (12, 12)
        # Secondary at (200, 205) should move to (212, 217), NOT snap to (208, 208)
        primary_start = (100.0, 100.0)
        raw_primary_end = (107.0, 107.0)

        # Snap primary
        snapped_primary = apply_snap_to_xy(raw_primary_end, snap_enabled=True, snap_mode="grid16", tile_size=16)
        # grid16 rounds 107 to nearest 16 -> 112
        assert snapped_primary == (112.0, 112.0)

        # Compute delta from snapped position
        delta = (snapped_primary[0] - primary_start[0], snapped_primary[1] - primary_start[1])
        assert delta == (12.0, 12.0)

        # Apply delta to secondary (NOT snapping secondary position)
        secondary_start = (200.0, 205.0)
        secondary_end = (secondary_start[0] + delta[0], secondary_start[1] + delta[1])

        # Secondary ends at non-grid-aligned position (which is correct!)
        assert secondary_end == (212.0, 217.0)
