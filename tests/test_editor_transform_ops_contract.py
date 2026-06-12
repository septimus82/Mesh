"""Contract tests for editor_transform_ops pure functions.

These tests verify the transform operations work correctly without any
arcade/pygame dependencies (pure unit tests).
"""

from __future__ import annotations

import copy

import pytest

from engine.editor.editor_transform_ops import (
    MoveEntityCommand,
    apply_move_command,
    apply_snap_to_xy,
    compute_dragged_xy,
    create_move_command_from_drag,
    invert_move_command,
)

# ------------------------------------------------------------------------------
# MoveEntityCommand dataclass tests
# ------------------------------------------------------------------------------


class TestMoveEntityCommand:
    """Tests for MoveEntityCommand dataclass."""

    def test_to_dict_includes_all_fields(self) -> None:
        """to_dict returns correct structure with type, entity_name, before, after."""
        cmd = MoveEntityCommand(entity_id="hero", start_xy=(100.0, 200.0), end_xy=(150.0, 250.0))
        result = cmd.to_dict()

        assert result["type"] == "MoveEntity"
        assert result["entity_name"] == "hero"
        assert result["before"] == {"x": 100.0, "y": 200.0}
        assert result["after"] == {"x": 150.0, "y": 250.0}

    def test_from_dict_roundtrip(self) -> None:
        """from_dict correctly reconstructs a command from its dict form."""
        original = MoveEntityCommand(entity_id="npc_1", start_xy=(32.0, 64.0), end_xy=(96.0, 128.0))
        serialized = original.to_dict()
        restored = MoveEntityCommand.from_dict(serialized)

        assert restored.entity_id == original.entity_id
        assert restored.start_xy == original.start_xy
        assert restored.end_xy == original.end_xy


# ------------------------------------------------------------------------------
# compute_dragged_xy tests
# ------------------------------------------------------------------------------


class TestComputeDraggedXY:
    """Tests for compute_dragged_xy helper."""

    def test_computes_delta_correctly(self) -> None:
        """Entity follows mouse delta from drag start."""
        # Entity starts at (100, 100), mouse starts at (50, 50), now at (80, 70)
        entity_start = (100.0, 100.0)
        drag_start_mouse = (50.0, 50.0)
        current_mouse = (80.0, 70.0)

        result = compute_dragged_xy(entity_start, drag_start_mouse, current_mouse)

        # Delta is (30, 20), so new position is (130, 120)
        assert result == (130.0, 120.0)

    def test_negative_delta(self) -> None:
        """Entity can move in negative direction."""
        entity_start = (200.0, 200.0)
        drag_start_mouse = (100.0, 100.0)
        current_mouse = (70.0, 60.0)  # moved -30, -40

        result = compute_dragged_xy(entity_start, drag_start_mouse, current_mouse)

        assert result == (170.0, 160.0)

    def test_zero_delta(self) -> None:
        """No movement when mouse hasn't moved."""
        entity_start = (50.0, 50.0)
        drag_start_mouse = (100.0, 100.0)
        current_mouse = (100.0, 100.0)

        result = compute_dragged_xy(entity_start, drag_start_mouse, current_mouse)

        assert result == (50.0, 50.0)


# ------------------------------------------------------------------------------
# apply_snap_to_xy tests
# ------------------------------------------------------------------------------


class TestApplySnapToXY:
    """Tests for apply_snap_to_xy helper."""

    def test_snap_disabled_returns_original(self) -> None:
        """When snap_enabled=False, returns input unchanged."""
        xy = (17.3, 23.7)
        result = apply_snap_to_xy(xy, snap_enabled=False, snap_mode="grid16", tile_size=16)
        assert result == xy

    def test_snap_grid16_rounds_to_16(self) -> None:
        """grid16 mode rounds to nearest 16 units."""
        # 23 is closer to 16 than 32
        result = apply_snap_to_xy((23.0, 42.0), snap_enabled=True, snap_mode="grid16", tile_size=16)
        assert result == (16.0, 48.0)

    def test_snap_grid8_rounds_to_8(self) -> None:
        """grid8 mode rounds to nearest 8 units."""
        result = apply_snap_to_xy((13.0, 21.0), snap_enabled=True, snap_mode="grid8", tile_size=16)
        assert result == (16.0, 24.0)

    def test_snap_tile_center(self) -> None:
        """tile_center mode snaps to center of tile."""
        # For 16px tiles, centers are at 8, 24, 40, etc.
        result = apply_snap_to_xy((20.0, 35.0), snap_enabled=True, snap_mode="tile_center", tile_size=16)
        assert result == (24.0, 40.0)

    def test_snap_unknown_mode_passes_through(self) -> None:
        """Unknown snap mode passes through unchanged (only known modes snap)."""
        result = apply_snap_to_xy((10.0, 10.0), snap_enabled=True, snap_mode="unknown", tile_size=16)
        # Unknown modes return input unchanged per snap_world_point behavior
        assert result == (10.0, 10.0)


# ------------------------------------------------------------------------------
# apply_move_command tests
# ------------------------------------------------------------------------------


class TestApplyMoveCommand:
    """Tests for apply_move_command helper."""

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

    def test_moves_only_target_entity(self, sample_scene: dict) -> None:
        """Only the entity matching entity_id is moved."""
        cmd = MoveEntityCommand(entity_id="npc_1", start_xy=(300.0, 400.0), end_xy=(350.0, 450.0))

        result = apply_move_command(sample_scene, cmd)

        # hero unchanged
        assert result["entities"][0]["x"] == 100
        assert result["entities"][0]["y"] == 200
        # npc_1 moved
        assert result["entities"][1]["x"] == 350.0
        assert result["entities"][1]["y"] == 450.0
        # chest unchanged
        assert result["entities"][2]["x"] == 500
        assert result["entities"][2]["y"] == 600

    def test_does_not_mutate_original(self, sample_scene: dict) -> None:
        """apply_move_command creates a deep copy and doesn't mutate input."""
        original = copy.deepcopy(sample_scene)
        cmd = MoveEntityCommand(entity_id="hero", start_xy=(100.0, 200.0), end_xy=(999.0, 999.0))

        apply_move_command(sample_scene, cmd)

        assert sample_scene == original

    def test_missing_entity_returns_unchanged(self) -> None:
        """If entity not found, returns scene unchanged."""
        scene = {"entities": [{"name": "hero", "x": 100, "y": 200}]}
        cmd = MoveEntityCommand(entity_id="missing", start_xy=(0.0, 0.0), end_xy=(50.0, 50.0))

        result = apply_move_command(scene, cmd)

        assert result["entities"][0]["x"] == 100
        assert result["entities"][0]["y"] == 200


# ------------------------------------------------------------------------------
# invert_move_command tests
# ------------------------------------------------------------------------------


class TestInvertMoveCommand:
    """Tests for invert_move_command helper."""

    def test_swaps_start_and_end(self) -> None:
        """Inverted command has start and end swapped."""
        cmd = MoveEntityCommand(entity_id="hero", start_xy=(100.0, 200.0), end_xy=(300.0, 400.0))

        inverted = invert_move_command(cmd)

        assert inverted.entity_id == "hero"
        assert inverted.start_xy == (300.0, 400.0)
        assert inverted.end_xy == (100.0, 200.0)

    def test_double_invert_returns_original(self) -> None:
        """Inverting twice returns the original values."""
        original = MoveEntityCommand(entity_id="npc", start_xy=(50.0, 60.0), end_xy=(70.0, 80.0))

        double_inverted = invert_move_command(invert_move_command(original))

        assert double_inverted.entity_id == original.entity_id
        assert double_inverted.start_xy == original.start_xy
        assert double_inverted.end_xy == original.end_xy


# ------------------------------------------------------------------------------
# create_move_command_from_drag tests
# ------------------------------------------------------------------------------


class TestCreateMoveCommandFromDrag:
    """Tests for create_move_command_from_drag helper."""

    def test_returns_none_when_no_movement(self) -> None:
        """Returns None if start and end positions are the same."""
        result = create_move_command_from_drag("hero", (100.0, 200.0), (100.0, 200.0))
        assert result is None

    def test_returns_command_when_moved(self) -> None:
        """Returns MoveEntityCommand when position changed."""
        result = create_move_command_from_drag("hero", (100.0, 200.0), (150.0, 250.0))

        assert result is not None
        assert result.entity_id == "hero"
        assert result.start_xy == (100.0, 200.0)
        assert result.end_xy == (150.0, 250.0)

    def test_handles_floating_point_precision(self) -> None:
        """Returns command even for small floating point movements."""
        result = create_move_command_from_drag("hero", (100.0, 200.0), (100.001, 200.0))
        assert result is not None
