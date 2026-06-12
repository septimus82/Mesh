"""Contract tests for editor_rotate_ops module.

Tests rotation operations as pure functions - headless, no arcade dependency.
"""

from __future__ import annotations

import math

import pytest

from engine.editor.editor_rotate_ops import (
    RotateEntitiesCommand,
    RotateEntityCommand,
    apply_rotate_entities,
    apply_rotate_entity,
    compute_angle_deg,
    compute_rotation_delta_deg,
    create_rotate_entities_command_from_drag,
    invert_rotate_entities,
    invert_rotate_entity,
    snap_rot_deg,
    wrap_deg,
)

# -----------------------------------------------------------------------------
# wrap_deg
# -----------------------------------------------------------------------------


class TestWrapDeg:
    """Tests for wrap_deg function."""

    def test_positive_within_range(self) -> None:
        assert wrap_deg(45.0) == 45.0
        assert wrap_deg(359.0) == 359.0

    def test_zero(self) -> None:
        assert wrap_deg(0.0) == 0.0

    def test_negative_wraps_positive(self) -> None:
        result = wrap_deg(-90.0)
        assert result == pytest.approx(270.0)

    def test_over_360_wraps(self) -> None:
        result = wrap_deg(450.0)
        assert result == pytest.approx(90.0)

    def test_multiple_rotations(self) -> None:
        result = wrap_deg(720.0 + 45.0)
        assert result == pytest.approx(45.0)

    def test_large_negative(self) -> None:
        result = wrap_deg(-720.0 - 45.0)
        assert result == pytest.approx(315.0)


# -----------------------------------------------------------------------------
# compute_angle_deg
# -----------------------------------------------------------------------------


class TestComputeAngleDeg:
    """Tests for compute_angle_deg function."""

    def test_right_is_zero(self) -> None:
        # Point directly to the right of pivot
        result = compute_angle_deg(0, 0, 10, 0)
        assert result == pytest.approx(0.0)

    def test_up_is_90(self) -> None:
        # Point directly above pivot
        result = compute_angle_deg(0, 0, 0, 10)
        assert result == pytest.approx(90.0)

    def test_left_is_180(self) -> None:
        # Point directly to the left of pivot
        result = compute_angle_deg(0, 0, -10, 0)
        assert result == pytest.approx(180.0)

    def test_down_is_270(self) -> None:
        # Point directly below pivot
        result = compute_angle_deg(0, 0, 0, -10)
        assert result == pytest.approx(270.0)

    def test_diagonal_45(self) -> None:
        result = compute_angle_deg(0, 0, 10, 10)
        assert result == pytest.approx(45.0)

    def test_same_point_returns_zero(self) -> None:
        result = compute_angle_deg(5, 5, 5, 5)
        assert result == 0.0


# -----------------------------------------------------------------------------
# compute_rotation_delta_deg
# -----------------------------------------------------------------------------


class TestComputeRotationDeltaDeg:
    """Tests for compute_rotation_delta_deg function."""

    def test_no_rotation(self) -> None:
        # Mouse at same angle from pivot
        delta = compute_rotation_delta_deg((0, 0), (10, 0), (10, 0))
        assert delta == pytest.approx(0.0)

    def test_positive_rotation_90(self) -> None:
        # Mouse from right (0°) to top (90°)
        delta = compute_rotation_delta_deg((0, 0), (10, 0), (0, 10))
        assert delta == pytest.approx(90.0)

    def test_negative_rotation_90(self) -> None:
        # Mouse from top (90°) to right (0°)
        delta = compute_rotation_delta_deg((0, 0), (0, 10), (10, 0))
        assert delta == pytest.approx(-90.0)

    def test_wrap_around_positive(self) -> None:
        # Mouse from nearly left-down to nearly left-up
        # Start at about 260° (just past down-left), end at about 100° (just past up)
        start_angle = 260
        end_angle = 100
        start = (math.cos(math.radians(start_angle)) * 10, math.sin(math.radians(start_angle)) * 10)
        end = (math.cos(math.radians(end_angle)) * 10, math.sin(math.radians(end_angle)) * 10)
        delta = compute_rotation_delta_deg((0, 0), start, end)
        # Should be about -160, not +200
        assert delta == pytest.approx(-160.0)

    def test_180_degree_turn(self) -> None:
        # Mouse from right (0°) to left (180°)
        delta = compute_rotation_delta_deg((0, 0), (10, 0), (-10, 0))
        assert abs(delta) == pytest.approx(180.0)


# -----------------------------------------------------------------------------
# snap_rot_deg
# -----------------------------------------------------------------------------


class TestSnapRotDeg:
    """Tests for snap_rot_deg function."""

    def test_snap_to_15_degrees(self) -> None:
        assert snap_rot_deg(7.0, 15.0) == pytest.approx(0.0)
        assert snap_rot_deg(8.0, 15.0) == pytest.approx(15.0)
        assert snap_rot_deg(22.0, 15.0) == pytest.approx(15.0)
        assert snap_rot_deg(23.0, 15.0) == pytest.approx(30.0)

    def test_snap_negative_values(self) -> None:
        assert snap_rot_deg(-7.0, 15.0) == pytest.approx(0.0)
        assert snap_rot_deg(-8.0, 15.0) == pytest.approx(-15.0)

    def test_snap_to_45_degrees(self) -> None:
        assert snap_rot_deg(20.0, 45.0) == pytest.approx(0.0)
        assert snap_rot_deg(25.0, 45.0) == pytest.approx(45.0)

    def test_exact_multiple_unchanged(self) -> None:
        assert snap_rot_deg(90.0, 15.0) == pytest.approx(90.0)
        assert snap_rot_deg(45.0, 15.0) == pytest.approx(45.0)


# -----------------------------------------------------------------------------
# RotateEntityCommand dataclass
# -----------------------------------------------------------------------------


class TestRotateEntityCommand:
    """Tests for RotateEntityCommand dataclass."""

    def test_creation(self) -> None:
        cmd = RotateEntityCommand(entity_id="ent1", start_rot_deg=0.0, end_rot_deg=45.0)
        assert cmd.entity_id == "ent1"
        assert cmd.start_rot_deg == 0.0
        assert cmd.end_rot_deg == 45.0

    def test_to_dict(self) -> None:
        cmd = RotateEntityCommand(entity_id="ent1", start_rot_deg=10.0, end_rot_deg=55.0)
        d = cmd.to_dict()
        assert d["type"] == "RotateEntity"
        assert d["entity_id"] == "ent1"
        assert d["before"] == 10.0
        assert d["after"] == 55.0

    def test_from_dict(self) -> None:
        d = {"entity_id": "ent2", "before": 90.0, "after": 180.0}
        cmd = RotateEntityCommand.from_dict(d)
        assert cmd.entity_id == "ent2"
        assert cmd.start_rot_deg == 90.0
        assert cmd.end_rot_deg == 180.0

    def test_roundtrip(self) -> None:
        original = RotateEntityCommand(entity_id="test", start_rot_deg=15.0, end_rot_deg=30.0)
        restored = RotateEntityCommand.from_dict(original.to_dict())
        assert restored == original


# -----------------------------------------------------------------------------
# RotateEntitiesCommand dataclass
# -----------------------------------------------------------------------------


class TestRotateEntitiesCommand:
    """Tests for RotateEntitiesCommand dataclass."""

    def test_creation(self) -> None:
        r1 = RotateEntityCommand(entity_id="e1", start_rot_deg=0.0, end_rot_deg=45.0)
        r2 = RotateEntityCommand(entity_id="e2", start_rot_deg=90.0, end_rot_deg=135.0)
        cmd = RotateEntitiesCommand(rotates=(r1, r2))
        assert len(cmd.rotates) == 2

    def test_to_dict(self) -> None:
        r1 = RotateEntityCommand(entity_id="e1", start_rot_deg=0.0, end_rot_deg=45.0)
        cmd = RotateEntitiesCommand(rotates=(r1,))
        d = cmd.to_dict()
        assert d["type"] == "RotateEntities"
        assert len(d["rotates"]) == 1
        assert d["rotates"][0]["entity_id"] == "e1"

    def test_from_dict(self) -> None:
        d = {
            "type": "RotateEntities",
            "rotates": [
                {"entity_id": "e1", "start_rot_deg": 0.0, "end_rot_deg": 45.0},
                {"entity_id": "e2", "start_rot_deg": 10.0, "end_rot_deg": 55.0},
            ],
        }
        cmd = RotateEntitiesCommand.from_dict(d)
        assert len(cmd.rotates) == 2
        assert cmd.rotates[0].entity_id == "e1"
        assert cmd.rotates[1].entity_id == "e2"

    def test_roundtrip(self) -> None:
        r1 = RotateEntityCommand(entity_id="e1", start_rot_deg=0.0, end_rot_deg=45.0)
        r2 = RotateEntityCommand(entity_id="e2", start_rot_deg=90.0, end_rot_deg=180.0)
        original = RotateEntitiesCommand(rotates=(r1, r2))
        restored = RotateEntitiesCommand.from_dict(original.to_dict())
        assert restored == original


# -----------------------------------------------------------------------------
# apply_rotate_entity / apply_rotate_entities
# -----------------------------------------------------------------------------


def _make_scene_json(entities: dict) -> dict:
    """Helper to create scene JSON with entities."""
    return {
        "entities": [
            {"id": eid, "rotation": data.get("rotation", 0.0)}
            for eid, data in entities.items()
        ]
    }


def _get_entity_rotation(scene_json: dict, entity_id: str) -> float | None:
    """Helper to get entity rotation from scene JSON."""
    for entity in scene_json.get("entities", []):
        if entity.get("id") == entity_id:
            return entity.get("rotation", 0.0)
    return None


class TestApplyRotateEntity:
    """Tests for apply_rotate_entity function."""

    def test_apply_rotation(self) -> None:
        scene = _make_scene_json({"e1": {"rotation": 0.0}})
        cmd = RotateEntityCommand(entity_id="e1", start_rot_deg=0.0, end_rot_deg=45.0)
        result = apply_rotate_entity(scene, cmd)
        assert _get_entity_rotation(result, "e1") == pytest.approx(45.0)

    def test_apply_to_nonexistent_entity(self) -> None:
        scene = _make_scene_json({})
        cmd = RotateEntityCommand(entity_id="missing", start_rot_deg=0.0, end_rot_deg=45.0)
        # Should not raise
        result = apply_rotate_entity(scene, cmd)
        assert _get_entity_rotation(result, "missing") is None

    def test_does_not_mutate_input(self) -> None:
        scene = _make_scene_json({"e1": {"rotation": 0.0}})
        cmd = RotateEntityCommand(entity_id="e1", start_rot_deg=0.0, end_rot_deg=45.0)
        _ = apply_rotate_entity(scene, cmd)
        # Original should be unchanged
        assert _get_entity_rotation(scene, "e1") == pytest.approx(0.0)


class TestApplyRotateEntities:
    """Tests for apply_rotate_entities function."""

    def test_apply_multiple_rotations(self) -> None:
        scene = _make_scene_json({
            "e1": {"rotation": 0.0},
            "e2": {"rotation": 90.0},
        })
        r1 = RotateEntityCommand(entity_id="e1", start_rot_deg=0.0, end_rot_deg=45.0)
        r2 = RotateEntityCommand(entity_id="e2", start_rot_deg=90.0, end_rot_deg=135.0)
        cmd = RotateEntitiesCommand(rotates=(r1, r2))
        result = apply_rotate_entities(scene, cmd)
        assert _get_entity_rotation(result, "e1") == pytest.approx(45.0)
        assert _get_entity_rotation(result, "e2") == pytest.approx(135.0)


# -----------------------------------------------------------------------------
# invert commands
# -----------------------------------------------------------------------------


class TestInvertRotateEntity:
    """Tests for invert_rotate_entity function."""

    def test_invert_swaps_start_end(self) -> None:
        cmd = RotateEntityCommand(entity_id="e1", start_rot_deg=0.0, end_rot_deg=45.0)
        inv = invert_rotate_entity(cmd)
        assert inv.entity_id == "e1"
        assert inv.start_rot_deg == 45.0
        assert inv.end_rot_deg == 0.0


class TestInvertRotateEntities:
    """Tests for invert_rotate_entities function."""

    def test_invert_all_rotations(self) -> None:
        r1 = RotateEntityCommand(entity_id="e1", start_rot_deg=0.0, end_rot_deg=45.0)
        r2 = RotateEntityCommand(entity_id="e2", start_rot_deg=90.0, end_rot_deg=180.0)
        cmd = RotateEntitiesCommand(rotates=(r1, r2))
        inv = invert_rotate_entities(cmd)
        assert len(inv.rotates) == 2
        assert inv.rotates[0].start_rot_deg == 45.0
        assert inv.rotates[0].end_rot_deg == 0.0
        assert inv.rotates[1].start_rot_deg == 180.0
        assert inv.rotates[1].end_rot_deg == 90.0


# -----------------------------------------------------------------------------
# create_rotate_entities_command_from_drag
# -----------------------------------------------------------------------------


class TestCreateRotateEntitiesCommandFromDrag:
    """Tests for create_rotate_entities_command_from_drag function."""

    def test_create_from_drag(self) -> None:
        start_rots = {"e1": 0.0, "e2": 45.0}
        delta_deg = 30.0
        cmd = create_rotate_entities_command_from_drag(start_rots, delta_deg)
        assert cmd is not None
        assert len(cmd.rotates) == 2
        # Rotation should apply delta to each start
        for rot in cmd.rotates:
            if rot.entity_id == "e1":
                assert rot.start_rot_deg == 0.0
                assert rot.end_rot_deg == pytest.approx(30.0)
            elif rot.entity_id == "e2":
                assert rot.start_rot_deg == 45.0
                assert rot.end_rot_deg == pytest.approx(75.0)

    def test_no_change_returns_none(self) -> None:
        start_rots = {"e1": 0.0, "e2": 45.0}
        delta_deg = 0.0
        cmd = create_rotate_entities_command_from_drag(start_rots, delta_deg)
        assert cmd is None

    def test_single_entity(self) -> None:
        start_rots = {"e1": 0.0}
        delta_deg = 90.0
        cmd = create_rotate_entities_command_from_drag(start_rots, delta_deg)
        assert cmd is not None
        assert len(cmd.rotates) == 1
        assert cmd.rotates[0].entity_id == "e1"
        assert cmd.rotates[0].end_rot_deg == pytest.approx(90.0)

    def test_empty_input(self) -> None:
        cmd = create_rotate_entities_command_from_drag({}, 45.0)
        assert cmd is None
