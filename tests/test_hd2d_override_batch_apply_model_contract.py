"""Contract tests for engine/editor/hd2d_override_batch_apply_model.py.

Tests the pure model functions for batch applying HD-2D overrides:
- Extracting entity positions from scene payload
- Selecting entities within radius
- Selecting entities by render_layer
- Computing deterministic batch targets
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from engine.editor.hd2d_override_batch_apply_model import (
    compute_batch_apply_targets,
    list_entities_with_positions,
    select_entities_in_radius,
    select_entities_same_render_layer,
)
from engine.editor.hd2d_entity_overrides_model import (
    apply_hd2d_entity_override_patch,
    clear_all_overrides,
)


# =============================================================================
# Test list_entities_with_positions
# =============================================================================


class TestListEntitiesWithPositions:
    """Tests for list_entities_with_positions function."""

    def test_empty_scene_returns_empty(self) -> None:
        """Empty scene should return empty list."""
        assert list_entities_with_positions({}) == []
        assert list_entities_with_positions({"entities": []}) == []

    def test_invalid_input_returns_empty(self) -> None:
        """Invalid input should return empty list."""
        assert list_entities_with_positions(None) == []  # type: ignore[arg-type]
        assert list_entities_with_positions([]) == []  # type: ignore[arg-type]

    def test_extracts_positions_from_list_entities(self) -> None:
        """Should extract positions from list-format entities."""
        scene = {
            "entities": [
                {"id": "entity_a", "x": 100.0, "y": 200.0},
                {"id": "entity_b", "x": 50.0, "y": 75.0, "render_layer": "foreground"},
            ]
        }
        result = list_entities_with_positions(scene)
        assert len(result) == 2
        # Should be sorted by entity_id
        assert result[0][0] == "entity_a"
        assert result[0][1] == 100.0
        assert result[0][2] == 200.0
        assert result[1][0] == "entity_b"
        assert result[1][3] == "foreground"

    def test_extracts_positions_from_dict_entities(self) -> None:
        """Should extract positions from dict-format entities."""
        scene = {
            "entities": {
                "entity_a": {"x": 100.0, "y": 200.0},
                "entity_b": {"x": 50.0, "y": 75.0},
            }
        }
        result = list_entities_with_positions(scene)
        assert len(result) == 2
        # Should be sorted by entity_id
        assert result[0][0] == "entity_a"
        assert result[1][0] == "entity_b"

    def test_skips_entities_without_position(self) -> None:
        """Should skip entities missing x or y."""
        scene = {
            "entities": [
                {"id": "no_x", "y": 100.0},
                {"id": "no_y", "x": 100.0},
                {"id": "has_both", "x": 50.0, "y": 50.0},
            ]
        }
        result = list_entities_with_positions(scene)
        assert len(result) == 1
        assert result[0][0] == "has_both"

    def test_results_are_deterministic(self) -> None:
        """Results should be sorted by entity_id for determinism."""
        scene = {
            "entities": [
                {"id": "z_entity", "x": 0.0, "y": 0.0},
                {"id": "a_entity", "x": 0.0, "y": 0.0},
                {"id": "m_entity", "x": 0.0, "y": 0.0},
            ]
        }
        result = list_entities_with_positions(scene)
        ids = [r[0] for r in result]
        assert ids == ["a_entity", "m_entity", "z_entity"]


# =============================================================================
# Test select_entities_in_radius
# =============================================================================


class TestSelectEntitiesInRadius:
    """Tests for select_entities_in_radius function."""

    def test_empty_entities_returns_empty(self) -> None:
        """Empty entities list should return empty."""
        assert select_entities_in_radius("center", 100.0, []) == []

    def test_center_not_found_returns_empty(self) -> None:
        """Missing center entity should return empty."""
        entities = [("other", 0.0, 0.0, None, None)]
        assert select_entities_in_radius("missing", 100.0, entities) == []

    def test_selects_entities_within_radius(self) -> None:
        """Should select entities within radius."""
        entities = [
            ("center", 0.0, 0.0, None, None),
            ("near", 50.0, 0.0, None, None),  # 50px away
            ("far", 200.0, 0.0, None, None),  # 200px away
        ]
        result = select_entities_in_radius("center", 100.0, entities)
        assert "center" in result
        assert "near" in result
        assert "far" not in result

    def test_excludes_center_when_requested(self) -> None:
        """Should exclude center entity when include_center=False."""
        entities = [
            ("center", 0.0, 0.0, None, None),
            ("near", 50.0, 0.0, None, None),
        ]
        result = select_entities_in_radius("center", 100.0, entities, include_center=False)
        assert "center" not in result
        assert "near" in result

    def test_radius_boundary(self) -> None:
        """Entity exactly on radius boundary should be included."""
        entities = [
            ("center", 0.0, 0.0, None, None),
            ("on_boundary", 100.0, 0.0, None, None),  # Exactly 100px
        ]
        result = select_entities_in_radius("center", 100.0, entities)
        assert "on_boundary" in result

    def test_results_are_sorted(self) -> None:
        """Results should be sorted for determinism."""
        entities = [
            ("center", 0.0, 0.0, None, None),
            ("z_near", 10.0, 0.0, None, None),
            ("a_near", 20.0, 0.0, None, None),
            ("m_near", 15.0, 0.0, None, None),
        ]
        result = select_entities_in_radius("center", 100.0, entities)
        assert result == ["a_near", "center", "m_near", "z_near"]

    def test_negative_radius_returns_empty(self) -> None:
        """Negative radius should return empty."""
        entities = [("center", 0.0, 0.0, None, None)]
        assert select_entities_in_radius("center", -10.0, entities) == []


# =============================================================================
# Test select_entities_same_render_layer
# =============================================================================


class TestSelectEntitiesSameRenderLayer:
    """Tests for select_entities_same_render_layer function."""

    def test_center_not_found_returns_empty(self) -> None:
        """Missing center entity should return empty."""
        entities = [("other", 0.0, 0.0, "layer1", None)]
        assert select_entities_same_render_layer("missing", entities) == []

    def test_selects_matching_render_layer(self) -> None:
        """Should select entities with same render_layer."""
        entities = [
            ("center", 0.0, 0.0, "foreground", None),
            ("same_layer", 100.0, 0.0, "foreground", None),
            ("diff_layer", 200.0, 0.0, "background", None),
        ]
        result = select_entities_same_render_layer("center", entities)
        assert "center" in result
        assert "same_layer" in result
        assert "diff_layer" not in result

    def test_none_layer_matches_none(self) -> None:
        """None render_layer should match other None."""
        entities = [
            ("center", 0.0, 0.0, None, None),
            ("also_none", 100.0, 0.0, None, None),
            ("has_layer", 200.0, 0.0, "layer1", None),
        ]
        result = select_entities_same_render_layer("center", entities)
        assert "center" in result
        assert "also_none" in result
        assert "has_layer" not in result

    def test_excludes_center_when_requested(self) -> None:
        """Should exclude center when include_center=False."""
        entities = [
            ("center", 0.0, 0.0, "layer1", None),
            ("same", 100.0, 0.0, "layer1", None),
        ]
        result = select_entities_same_render_layer("center", entities, include_center=False)
        assert "center" not in result
        assert "same" in result

    def test_results_are_sorted(self) -> None:
        """Results should be sorted for determinism."""
        entities = [
            ("center", 0.0, 0.0, "layer1", None),
            ("z_same", 0.0, 0.0, "layer1", None),
            ("a_same", 0.0, 0.0, "layer1", None),
        ]
        result = select_entities_same_render_layer("center", entities)
        assert result == ["a_same", "center", "z_same"]


# =============================================================================
# Test compute_batch_apply_targets
# =============================================================================


class TestComputeBatchApplyTargets:
    """Tests for compute_batch_apply_targets function."""

    def test_radius_mode(self) -> None:
        """Should use radius selection in radius mode."""
        scene = {
            "entities": [
                {"id": "center", "x": 0.0, "y": 0.0},
                {"id": "near", "x": 50.0, "y": 0.0},
                {"id": "far", "x": 200.0, "y": 0.0},
            ]
        }
        result = compute_batch_apply_targets(scene, "center", "radius", radius_px=100.0)
        assert "center" in result
        assert "near" in result
        assert "far" not in result

    def test_layer_mode(self) -> None:
        """Should use layer selection in layer mode."""
        scene = {
            "entities": [
                {"id": "center", "x": 0.0, "y": 0.0, "render_layer": "fg"},
                {"id": "same_layer", "x": 1000.0, "y": 0.0, "render_layer": "fg"},
                {"id": "diff_layer", "x": 10.0, "y": 0.0, "render_layer": "bg"},
            ]
        }
        result = compute_batch_apply_targets(scene, "center", "layer")
        assert "center" in result
        assert "same_layer" in result
        assert "diff_layer" not in result

    def test_invalid_mode_returns_empty(self) -> None:
        """Invalid mode should return empty list."""
        scene = {"entities": [{"id": "center", "x": 0.0, "y": 0.0}]}
        result = compute_batch_apply_targets(scene, "center", "invalid")  # type: ignore[arg-type]
        assert result == []

    def test_batch_targets_radius_deterministic(self) -> None:
        """Batch targets should be deterministic across calls."""
        scene = {
            "entities": [
                {"id": "z_entity", "x": 10.0, "y": 0.0},
                {"id": "center", "x": 0.0, "y": 0.0},
                {"id": "a_entity", "x": 20.0, "y": 0.0},
                {"id": "m_entity", "x": 15.0, "y": 0.0},
            ]
        }
        # Call multiple times
        result1 = compute_batch_apply_targets(scene, "center", "radius", radius_px=100.0)
        result2 = compute_batch_apply_targets(scene, "center", "radius", radius_px=100.0)
        result3 = compute_batch_apply_targets(scene, "center", "radius", radius_px=100.0)

        # All should be identical and sorted
        assert result1 == result2 == result3
        assert result1 == sorted(result1)

    def test_batch_targets_layer_deterministic(self) -> None:
        """Batch targets by layer should be deterministic."""
        scene = {
            "entities": [
                {"id": "z_entity", "x": 10.0, "y": 0.0, "render_layer": "fg"},
                {"id": "center", "x": 0.0, "y": 0.0, "render_layer": "fg"},
                {"id": "a_entity", "x": 20.0, "y": 0.0, "render_layer": "fg"},
            ]
        }
        result1 = compute_batch_apply_targets(scene, "center", "layer")
        result2 = compute_batch_apply_targets(scene, "center", "layer")

        assert result1 == result2
        assert result1 == sorted(result1)


# =============================================================================
# Test Batch Apply Integration (using model functions)
# =============================================================================


class TestBatchApplyIntegration:
    """Integration tests for batch apply using model functions."""

    def test_batch_apply_merge_changes_multiple_entities(self) -> None:
        """Batch apply merge should apply clipboard to multiple entities."""
        scene = {
            "entities": [
                {"id": "center", "x": 0.0, "y": 0.0, "shadow_enabled": True},
                {"id": "near", "x": 50.0, "y": 0.0, "outline_enabled": False},
            ]
        }
        clipboard = {"depth_tint_enabled": True}

        # Get targets
        targets = compute_batch_apply_targets(scene, "center", "radius", radius_px=100.0)
        assert len(targets) == 2

        # Apply merge to each target
        current = copy.deepcopy(scene)
        for entity_id in targets:
            current = apply_hd2d_entity_override_patch(current, entity_id, clipboard)

        # Both entities should have clipboard applied, original overrides preserved
        center = current["entities"][0]
        near = current["entities"][1]

        assert center["shadow_enabled"] is True  # Preserved
        assert center["depth_tint_enabled"] is True  # Applied
        assert near["outline_enabled"] is False  # Preserved
        assert near["depth_tint_enabled"] is True  # Applied

    def test_batch_apply_replace_clears_then_applies(self) -> None:
        """Batch apply replace should clear all overrides first, then apply clipboard."""
        scene = {
            "entities": [
                {"id": "center", "x": 0.0, "y": 0.0, "shadow_enabled": True},
                {"id": "near", "x": 50.0, "y": 0.0, "outline_enabled": False},
            ]
        }
        clipboard = {"depth_tint_enabled": True}

        # Get targets
        targets = compute_batch_apply_targets(scene, "center", "radius", radius_px=100.0)

        # Apply replace to each target (clear first, then apply)
        current = copy.deepcopy(scene)
        for entity_id in targets:
            current = clear_all_overrides(current, entity_id)
            current = apply_hd2d_entity_override_patch(current, entity_id, clipboard)

        # Original overrides should be cleared, only clipboard applied
        center = current["entities"][0]
        near = current["entities"][1]

        assert center.get("shadow_enabled") is None  # Cleared
        assert center["depth_tint_enabled"] is True  # Applied
        assert near.get("outline_enabled") is None  # Cleared
        assert near["depth_tint_enabled"] is True  # Applied

    def test_batch_apply_produces_single_consistent_result(self) -> None:
        """Batch apply should produce consistent results (for single undo)."""
        scene = {
            "entities": [
                {"id": "a", "x": 10.0, "y": 0.0},
                {"id": "center", "x": 0.0, "y": 0.0},
                {"id": "z", "x": 20.0, "y": 0.0},
            ]
        }
        clipboard = {"shadow_enabled": True, "outline_strength": 0.5}

        # Apply twice and compare
        targets = compute_batch_apply_targets(scene, "center", "radius", radius_px=100.0)

        current1 = copy.deepcopy(scene)
        for entity_id in targets:
            current1 = apply_hd2d_entity_override_patch(current1, entity_id, clipboard)

        current2 = copy.deepcopy(scene)
        for entity_id in targets:
            current2 = apply_hd2d_entity_override_patch(current2, entity_id, clipboard)

        # Results should be identical
        assert current1 == current2
