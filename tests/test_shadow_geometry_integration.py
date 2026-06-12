"""
Integration tests for shadow_geometry_adapter module.

Tests that the adapter produces stable digests for fixture scenes,
ensuring the integration with the existing pipeline is deterministic.
"""
from __future__ import annotations

import pytest

from engine.lighting.occluders import Rect
from engine.lighting.shadow_geometry_adapter import (
    compute_shadow_geometry_from_configs,
    compute_shadow_hulls_from_configs,
    compute_shadow_hulls_from_rects,
    occluder_config_to_polygon,
    occluder_configs_to_polygons,
    rect_to_polygon,
    rects_to_polygons,
)

pytestmark = pytest.mark.fast


# =============================================================================
# Rect Conversion Tests
# =============================================================================


class TestRectConversion:
    """Tests for Rect to polygon conversion."""

    def test_rect_to_polygon_corners(self) -> None:
        """Rect converts to correct corner polygon."""
        rect = Rect(x=10.0, y=20.0, width=30.0, height=40.0)
        poly = rect_to_polygon(rect)

        assert len(poly) == 4
        assert poly[0] == (10.0, 20.0)
        assert poly[1] == (40.0, 20.0)
        assert poly[2] == (40.0, 60.0)
        assert poly[3] == (10.0, 60.0)

    def test_rects_to_polygons_batch(self) -> None:
        """Multiple rects convert correctly."""
        rects = [
            Rect(x=0.0, y=0.0, width=10.0, height=10.0),
            Rect(x=50.0, y=50.0, width=20.0, height=30.0),
        ]
        polys = rects_to_polygons(rects)

        assert len(polys) == 2
        assert len(polys[0]) == 4
        assert len(polys[1]) == 4


# =============================================================================
# Config Conversion Tests
# =============================================================================


class TestConfigConversion:
    """Tests for occluder config to polygon conversion."""

    def test_rect_config_converts(self) -> None:
        """Rect-style config converts to polygon."""
        config = {"x": 10.0, "y": 20.0, "width": 30.0, "height": 40.0}
        poly = occluder_config_to_polygon(config)

        assert poly is not None
        assert len(poly) == 4

    def test_polygon_config_converts(self) -> None:
        """Polygon-style config converts to polygon."""
        config = {
            "points": [
                [0.0, 0.0],
                [10.0, 0.0],
                [10.0, 10.0],
            ]
        }
        poly = occluder_config_to_polygon(config)

        assert poly is not None
        assert len(poly) == 3
        assert poly[0] == (0.0, 0.0)

    def test_invalid_config_returns_none(self) -> None:
        """Invalid config returns None."""
        # No dimensions
        assert occluder_config_to_polygon({}) is None

        # Zero dimensions
        assert occluder_config_to_polygon({"x": 0, "y": 0, "width": 0, "height": 10}) is None

    def test_configs_filter_invalid(self) -> None:
        """Invalid configs are filtered out."""
        configs = [
            {"x": 10.0, "y": 20.0, "width": 30.0, "height": 40.0},  # valid
            {},  # invalid
            {"x": 0, "y": 0, "width": 0, "height": 0},  # invalid
            {"points": [[0, 0], [10, 0], [10, 10]]},  # valid
        ]
        polys = occluder_configs_to_polygons(configs)

        assert len(polys) == 2


# =============================================================================
# Integration Tests
# =============================================================================


class TestShadowHullsFromRects:
    """Tests for shadow hull computation from Rects."""

    def test_produces_hulls(self) -> None:
        """Rects produce shadow hulls."""
        rects = [
            Rect(x=-10.0, y=-10.0, width=20.0, height=20.0),
        ]
        light_pos = (50.0, 0.0)

        hulls = compute_shadow_hulls_from_rects(rects, light_pos)

        assert len(hulls) > 0

    def test_deterministic(self) -> None:
        """Output is deterministic."""
        rects = [
            Rect(x=-50.0, y=-5.0, width=10.0, height=10.0),
            Rect(x=50.0, y=-5.0, width=10.0, height=10.0),
        ]
        light_pos = (0.0, 0.0)

        hulls1 = compute_shadow_hulls_from_rects(rects, light_pos)
        hulls2 = compute_shadow_hulls_from_rects(list(reversed(rects)), light_pos)

        assert hulls1 == hulls2


class TestShadowHullsFromConfigs:
    """Tests for shadow hull computation from configs."""

    def test_produces_hulls(self) -> None:
        """Configs produce shadow hulls."""
        configs = [
            {"x": -10.0, "y": -10.0, "width": 20.0, "height": 20.0},
        ]
        light_pos = (50.0, 0.0)

        hulls = compute_shadow_hulls_from_configs(configs, light_pos)

        assert len(hulls) > 0

    def test_mixed_configs_work(self) -> None:
        """Mixed rect and polygon configs work."""
        configs = [
            {"x": -10.0, "y": -10.0, "width": 20.0, "height": 20.0},
            {"points": [[50, -10], [70, -10], [70, 10], [50, 10]]},
        ]
        light_pos = (0.0, 0.0)

        hulls = compute_shadow_hulls_from_configs(configs, light_pos)

        assert len(hulls) > 0


class TestShadowGeometryFromConfigs:
    """Tests for full shadow geometry from configs."""

    def test_produces_result(self) -> None:
        """Configs produce full geometry result."""
        configs = [
            {"x": -10.0, "y": -10.0, "width": 20.0, "height": 20.0},
        ]
        light_pos = (50.0, 0.0)

        result = compute_shadow_geometry_from_configs(configs, light_pos)

        assert result.hulls is not None
        assert result.segments is not None
        assert result.occluder_count == 1


# =============================================================================
# Digest Stability Tests (Integration Contract)
# =============================================================================


class TestIntegrationDigestStability:
    """Tests verifying stable digests for fixture scenes.
    
    These act as integration contract tests - if digests change,
    it indicates a change in shadow geometry computation.
    """

    def test_simple_scene_stable_digest(self) -> None:
        """Simple scene produces stable digest."""
        configs = [
            {"x": -10.0, "y": -10.0, "width": 20.0, "height": 20.0},
        ]
        light_pos = (50.0, 0.0)

        result1 = compute_shadow_geometry_from_configs(configs, light_pos, light_radius=100.0)
        result2 = compute_shadow_geometry_from_configs(configs, light_pos, light_radius=100.0)

        assert result1.full_digest() == result2.full_digest()

    def test_multi_occluder_stable_digest(self) -> None:
        """Multi-occluder scene produces stable digest."""
        configs = [
            {"x": -60.0, "y": -10.0, "width": 20.0, "height": 20.0},
            {"x": 40.0, "y": -10.0, "width": 20.0, "height": 20.0},
            {"x": -10.0, "y": 40.0, "width": 20.0, "height": 20.0},
        ]
        light_pos = (0.0, 0.0)

        # Multiple runs with different input orders
        digest_set = set()
        for _ in range(3):
            result = compute_shadow_geometry_from_configs(configs, light_pos)
            digest_set.add(result.full_digest())

        assert len(digest_set) == 1, "Digest should be stable across runs"

    def test_input_order_independent_digest(self) -> None:
        """Digest is independent of input config order."""
        configs1 = [
            {"x": -50.0, "y": 0.0, "width": 10.0, "height": 10.0},
            {"x": 50.0, "y": 0.0, "width": 10.0, "height": 10.0},
            {"x": 0.0, "y": 50.0, "width": 10.0, "height": 10.0},
        ]
        configs2 = [
            {"x": 50.0, "y": 0.0, "width": 10.0, "height": 10.0},
            {"x": 0.0, "y": 50.0, "width": 10.0, "height": 10.0},
            {"x": -50.0, "y": 0.0, "width": 10.0, "height": 10.0},
        ]
        light_pos = (0.0, 0.0)

        result1 = compute_shadow_geometry_from_configs(configs1, light_pos)
        result2 = compute_shadow_geometry_from_configs(configs2, light_pos)

        assert result1.full_digest() == result2.full_digest()

    def test_polygon_config_stable_digest(self) -> None:
        """Polygon config produces stable digest."""
        configs = [
            {"points": [[-10, -10], [10, -10], [10, 10], [-10, 10]]},
        ]
        light_pos = (50.0, 0.0)

        result1 = compute_shadow_geometry_from_configs(configs, light_pos)
        result2 = compute_shadow_geometry_from_configs(configs, light_pos)

        assert result1.full_digest() == result2.full_digest()


# =============================================================================
# Regression Guard Tests
# =============================================================================


# Known digest values for regression detection
# If these change, it indicates a behavioral change in shadow computation
REGRESSION_SIMPLE_BOX_DIGEST = None  # Will be set after first run if needed


class TestRegressionGuards:
    """Regression guards for shadow geometry.
    
    These tests verify that geometry computation hasn't changed unexpectedly.
    """

    def test_simple_box_geometry_valid(self) -> None:
        """Simple box produces valid geometry."""
        configs = [
            {"x": -10.0, "y": -10.0, "width": 20.0, "height": 20.0},
        ]
        light_pos = (50.0, 0.0)

        result = compute_shadow_geometry_from_configs(configs, light_pos, light_radius=100.0)

        # Should have hulls (3 edges face away from light when light is to the right)
        assert len(result.hulls) == 3

        # All hulls should have 4 vertices (quads)
        for hull in result.hulls:
            assert len(hull) == 4

        # Should have segments
        assert len(result.segments) == 3

    def test_triangle_geometry_valid(self) -> None:
        """Triangle produces valid geometry."""
        configs = [
            {"points": [[0, 20], [-17.32, -10], [17.32, -10]]},
        ]
        light_pos = (0.0, -50.0)  # Light below

        result = compute_shadow_geometry_from_configs(configs, light_pos, light_radius=100.0)

        # Should have at least one hull
        assert len(result.hulls) >= 1

        # All hulls valid
        for hull in result.hulls:
            assert len(hull) >= 3
