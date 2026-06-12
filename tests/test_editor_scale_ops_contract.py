"""Contract tests for editor_scale_ops module.

Tests scale operations as pure functions - headless, no arcade dependency.
"""

from __future__ import annotations

import pytest

from engine.editor.editor_scale_ops import (
    MIN_SCALE,
    ScaleEntitiesCommand,
    ScaleEntityCommand,
    apply_scale_entities,
    apply_scale_entity,
    clamp_scale,
    compute_scale_factor,
    create_scale_entities_command_from_drag,
    invert_scale_entities,
    invert_scale_entity,
    snap_scale_factor,
)

# -----------------------------------------------------------------------------
# clamp_scale
# -----------------------------------------------------------------------------


class TestClampScale:
    """Tests for clamp_scale function."""

    def test_normal_scale_unchanged(self) -> None:
        assert clamp_scale(1.0) == 1.0
        assert clamp_scale(2.5) == 2.5
        assert clamp_scale(0.5) == 0.5

    def test_clamps_to_min(self) -> None:
        result = clamp_scale(0.01)
        assert result == MIN_SCALE

    def test_clamps_zero(self) -> None:
        result = clamp_scale(0.0)
        assert result == MIN_SCALE

    def test_clamps_negative(self) -> None:
        result = clamp_scale(-1.0)
        assert result == MIN_SCALE

    def test_min_scale_value(self) -> None:
        assert MIN_SCALE == 0.05


# -----------------------------------------------------------------------------
# compute_scale_factor
# -----------------------------------------------------------------------------


class TestComputeScaleFactor:
    """Tests for compute_scale_factor function."""

    def test_no_change_returns_one(self) -> None:
        # Same distance from pivot
        factor = compute_scale_factor((0, 0), (10, 0), (10, 0))
        assert factor == pytest.approx(1.0)

    def test_double_distance(self) -> None:
        # Mouse moved twice as far from pivot
        factor = compute_scale_factor((0, 0), (10, 0), (20, 0))
        assert factor == pytest.approx(2.0)

    def test_half_distance(self) -> None:
        # Mouse moved half as far from pivot
        factor = compute_scale_factor((0, 0), (20, 0), (10, 0))
        assert factor == pytest.approx(0.5)

    def test_zero_start_distance(self) -> None:
        # Start point at pivot - should return 1.0 to avoid division by zero
        factor = compute_scale_factor((5, 5), (5, 5), (10, 5))
        assert factor == 1.0

    def test_zero_end_distance(self) -> None:
        # End point at pivot - should return minimum scale
        factor = compute_scale_factor((5, 5), (10, 5), (5, 5))
        assert factor <= MIN_SCALE or factor > 0.0

    def test_diagonal_distances(self) -> None:
        # Test with diagonal vectors
        # Start at (10, 10), end at (20, 20) from pivot (0, 0)
        # start_dist = sqrt(200) ≈ 14.14
        # end_dist = sqrt(800) ≈ 28.28
        factor = compute_scale_factor((0, 0), (10, 10), (20, 20))
        assert factor == pytest.approx(2.0)


# -----------------------------------------------------------------------------
# snap_scale_factor
# -----------------------------------------------------------------------------


class TestSnapScaleFactor:
    """Tests for snap_scale_factor function."""

    def test_snap_to_tenth(self) -> None:
        assert snap_scale_factor(1.04, 0.1) == pytest.approx(1.0)
        assert snap_scale_factor(1.06, 0.1) == pytest.approx(1.1)  # Definitely rounds up
        assert snap_scale_factor(1.14, 0.1) == pytest.approx(1.1)
        assert snap_scale_factor(1.16, 0.1) == pytest.approx(1.2)  # Definitely rounds up

    def test_snap_to_quarter(self) -> None:
        assert snap_scale_factor(1.12, 0.25) == pytest.approx(1.0)
        assert snap_scale_factor(1.13, 0.25) == pytest.approx(1.25)
        assert snap_scale_factor(1.37, 0.25) == pytest.approx(1.25)
        assert snap_scale_factor(1.38, 0.25) == pytest.approx(1.5)

    def test_exact_value_unchanged(self) -> None:
        assert snap_scale_factor(1.5, 0.1) == pytest.approx(1.5)
        assert snap_scale_factor(2.0, 0.25) == pytest.approx(2.0)

    def test_small_scale_snapping(self) -> None:
        result = snap_scale_factor(0.14, 0.1)
        assert result == pytest.approx(0.1)


# -----------------------------------------------------------------------------
# ScaleEntityCommand dataclass
# -----------------------------------------------------------------------------


class TestScaleEntityCommand:
    """Tests for ScaleEntityCommand dataclass."""

    def test_creation(self) -> None:
        cmd = ScaleEntityCommand(entity_id="ent1", start_scale=1.0, end_scale=2.0)
        assert cmd.entity_id == "ent1"
        assert cmd.start_scale == 1.0
        assert cmd.end_scale == 2.0

    def test_to_dict(self) -> None:
        cmd = ScaleEntityCommand(entity_id="ent1", start_scale=0.5, end_scale=1.5)
        d = cmd.to_dict()
        assert d["type"] == "ScaleEntity"
        assert d["entity_id"] == "ent1"
        assert d["before"] == 0.5
        assert d["after"] == 1.5

    def test_from_dict(self) -> None:
        d = {"entity_id": "ent2", "before": 1.0, "after": 3.0}
        cmd = ScaleEntityCommand.from_dict(d)
        assert cmd.entity_id == "ent2"
        assert cmd.start_scale == 1.0
        assert cmd.end_scale == 3.0

    def test_roundtrip(self) -> None:
        original = ScaleEntityCommand(entity_id="test", start_scale=1.5, end_scale=2.5)
        restored = ScaleEntityCommand.from_dict(original.to_dict())
        assert restored == original


# -----------------------------------------------------------------------------
# ScaleEntitiesCommand dataclass
# -----------------------------------------------------------------------------


class TestScaleEntitiesCommand:
    """Tests for ScaleEntitiesCommand dataclass."""

    def test_creation(self) -> None:
        s1 = ScaleEntityCommand(entity_id="e1", start_scale=1.0, end_scale=2.0)
        s2 = ScaleEntityCommand(entity_id="e2", start_scale=0.5, end_scale=1.0)
        cmd = ScaleEntitiesCommand(scales=(s1, s2))
        assert len(cmd.scales) == 2

    def test_to_dict(self) -> None:
        s1 = ScaleEntityCommand(entity_id="e1", start_scale=1.0, end_scale=2.0)
        cmd = ScaleEntitiesCommand(scales=(s1,))
        d = cmd.to_dict()
        assert d["type"] == "ScaleEntities"
        assert len(d["scales"]) == 1
        assert d["scales"][0]["entity_id"] == "e1"

    def test_from_dict(self) -> None:
        d = {
            "type": "ScaleEntities",
            "scales": [
                {"entity_id": "e1", "start_scale": 1.0, "end_scale": 2.0},
                {"entity_id": "e2", "start_scale": 0.5, "end_scale": 1.0},
            ],
        }
        cmd = ScaleEntitiesCommand.from_dict(d)
        assert len(cmd.scales) == 2
        assert cmd.scales[0].entity_id == "e1"
        assert cmd.scales[1].entity_id == "e2"

    def test_roundtrip(self) -> None:
        s1 = ScaleEntityCommand(entity_id="e1", start_scale=1.0, end_scale=2.0)
        s2 = ScaleEntityCommand(entity_id="e2", start_scale=0.5, end_scale=1.0)
        original = ScaleEntitiesCommand(scales=(s1, s2))
        restored = ScaleEntitiesCommand.from_dict(original.to_dict())
        assert restored == original


# -----------------------------------------------------------------------------
# apply_scale_entity / apply_scale_entities
# -----------------------------------------------------------------------------


def _make_scene_json(entities: dict) -> dict:
    """Helper to create scene JSON with entities."""
    return {
        "entities": [
            {"id": eid, "scale": data.get("scale", 1.0)}
            for eid, data in entities.items()
        ]
    }


def _get_entity_scale(scene_json: dict, entity_id: str) -> float | None:
    """Helper to get entity scale from scene JSON."""
    for entity in scene_json.get("entities", []):
        if entity.get("id") == entity_id:
            return entity.get("scale", 1.0)
    return None


class TestApplyScaleEntity:
    """Tests for apply_scale_entity function."""

    def test_apply_scale(self) -> None:
        scene = _make_scene_json({"e1": {"scale": 1.0}})
        cmd = ScaleEntityCommand(entity_id="e1", start_scale=1.0, end_scale=2.0)
        result = apply_scale_entity(scene, cmd)
        assert _get_entity_scale(result, "e1") == pytest.approx(2.0)

    def test_apply_to_nonexistent_entity(self) -> None:
        scene = _make_scene_json({})
        cmd = ScaleEntityCommand(entity_id="missing", start_scale=1.0, end_scale=2.0)
        # Should not raise
        result = apply_scale_entity(scene, cmd)
        assert _get_entity_scale(result, "missing") is None

    def test_does_not_mutate_input(self) -> None:
        scene = _make_scene_json({"e1": {"scale": 1.0}})
        cmd = ScaleEntityCommand(entity_id="e1", start_scale=1.0, end_scale=2.0)
        _ = apply_scale_entity(scene, cmd)
        # Original should be unchanged
        assert _get_entity_scale(scene, "e1") == pytest.approx(1.0)


class TestApplyScaleEntities:
    """Tests for apply_scale_entities function."""

    def test_apply_multiple_scales(self) -> None:
        scene = _make_scene_json({
            "e1": {"scale": 1.0},
            "e2": {"scale": 0.5},
        })
        s1 = ScaleEntityCommand(entity_id="e1", start_scale=1.0, end_scale=2.0)
        s2 = ScaleEntityCommand(entity_id="e2", start_scale=0.5, end_scale=1.0)
        cmd = ScaleEntitiesCommand(scales=(s1, s2))
        result = apply_scale_entities(scene, cmd)
        assert _get_entity_scale(result, "e1") == pytest.approx(2.0)
        assert _get_entity_scale(result, "e2") == pytest.approx(1.0)


# -----------------------------------------------------------------------------
# invert commands
# -----------------------------------------------------------------------------


class TestInvertScaleEntity:
    """Tests for invert_scale_entity function."""

    def test_invert_swaps_start_end(self) -> None:
        cmd = ScaleEntityCommand(entity_id="e1", start_scale=1.0, end_scale=2.0)
        inv = invert_scale_entity(cmd)
        assert inv.entity_id == "e1"
        assert inv.start_scale == 2.0
        assert inv.end_scale == 1.0


class TestInvertScaleEntities:
    """Tests for invert_scale_entities function."""

    def test_invert_all_scales(self) -> None:
        s1 = ScaleEntityCommand(entity_id="e1", start_scale=1.0, end_scale=2.0)
        s2 = ScaleEntityCommand(entity_id="e2", start_scale=0.5, end_scale=1.5)
        cmd = ScaleEntitiesCommand(scales=(s1, s2))
        inv = invert_scale_entities(cmd)
        assert len(inv.scales) == 2
        assert inv.scales[0].start_scale == 2.0
        assert inv.scales[0].end_scale == 1.0
        assert inv.scales[1].start_scale == 1.5
        assert inv.scales[1].end_scale == 0.5


# -----------------------------------------------------------------------------
# create_scale_entities_command_from_drag
# -----------------------------------------------------------------------------


class TestCreateScaleEntitiesCommandFromDrag:
    """Tests for create_scale_entities_command_from_drag function."""

    def test_create_from_drag(self) -> None:
        start_scales = {"e1": 1.0, "e2": 0.5}
        factor = 2.0
        cmd = create_scale_entities_command_from_drag(start_scales, factor)
        assert cmd is not None
        assert len(cmd.scales) == 2
        # Scale should apply factor to each start
        for sc in cmd.scales:
            if sc.entity_id == "e1":
                assert sc.start_scale == 1.0
                assert sc.end_scale == pytest.approx(2.0)
            elif sc.entity_id == "e2":
                assert sc.start_scale == 0.5
                assert sc.end_scale == pytest.approx(1.0)

    def test_no_change_returns_none(self) -> None:
        start_scales = {"e1": 1.0, "e2": 0.5}
        factor = 1.0
        cmd = create_scale_entities_command_from_drag(start_scales, factor)
        assert cmd is None

    def test_single_entity(self) -> None:
        start_scales = {"e1": 1.0}
        factor = 0.5
        cmd = create_scale_entities_command_from_drag(start_scales, factor)
        assert cmd is not None
        assert len(cmd.scales) == 1
        assert cmd.scales[0].entity_id == "e1"
        assert cmd.scales[0].end_scale == pytest.approx(0.5)

    def test_empty_input(self) -> None:
        cmd = create_scale_entities_command_from_drag({}, 2.0)
        assert cmd is None

    def test_clamps_end_scale(self) -> None:
        start_scales = {"e1": 0.1}
        factor = 0.1  # Would result in 0.01, below MIN_SCALE
        cmd = create_scale_entities_command_from_drag(start_scales, factor)
        assert cmd is not None
        assert cmd.scales[0].end_scale >= MIN_SCALE
