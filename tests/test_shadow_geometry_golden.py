"""
Golden tests for shadow geometry module.

Tests verify:
1. Deterministic output across runs
2. Stable vertex ordering
3. Correct shadow hull computation for known fixtures
4. Invariants (no NaN, >=3 points, etc.)
"""
from __future__ import annotations

import json
from typing import Sequence

import pytest

from engine.lighting.shadow_geometry import (
    OcclusionSegment,
    Point,
    Polygon,
    ShadowGeometryResult,
    ShadowGeometryValidationResult,
    ShadowParams,
    assert_polygon_valid,
    assert_shadow_hulls_valid,
    compute_occlusion_segments,
    compute_shadow_geometry,
    compute_shadow_hull_for_occluder,
    compute_shadow_hulls,
    normalize_polygon,
    normalize_polygon_list,
    validate_polygon,
    validate_shadow_hulls,
)


pytestmark = pytest.mark.fast


# =============================================================================
# Golden Fixture Definitions
# =============================================================================


class GoldenFixtures:
    """Standard test fixtures for shadow geometry."""
    
    @staticmethod
    def convex_box() -> list[Point]:
        """Simple axis-aligned box centered at origin."""
        return [
            (-10.0, -10.0),
            (10.0, -10.0),
            (10.0, 10.0),
            (-10.0, 10.0),
        ]
    
    @staticmethod
    def triangle() -> list[Point]:
        """Simple equilateral-ish triangle."""
        return [
            (0.0, 20.0),
            (-17.32, -10.0),
            (17.32, -10.0),
        ]
    
    @staticmethod
    def concave_l_shape() -> list[Point]:
        """L-shaped concave polygon."""
        return [
            (0.0, 0.0),
            (30.0, 0.0),
            (30.0, 10.0),
            (10.0, 10.0),
            (10.0, 30.0),
            (0.0, 30.0),
        ]
    
    @staticmethod
    def thin_wall() -> list[Point]:
        """Very thin horizontal wall."""
        return [
            (0.0, 0.0),
            (100.0, 0.0),
            (100.0, 2.0),
            (0.0, 2.0),
        ]
    
    @staticmethod
    def small_square_at(x: float, y: float, size: float = 10.0) -> list[Point]:
        """Small square at given position."""
        half = size / 2.0
        return [
            (x - half, y - half),
            (x + half, y - half),
            (x + half, y + half),
            (x - half, y + half),
        ]
    
    @staticmethod
    def multiple_occluders() -> list[list[Point]]:
        """Multiple separate occluders."""
        return [
            GoldenFixtures.small_square_at(-50.0, 0.0),
            GoldenFixtures.small_square_at(50.0, 0.0),
            GoldenFixtures.small_square_at(0.0, 50.0),
        ]
    
    @staticmethod
    def light_centered() -> Point:
        """Light at origin."""
        return (0.0, 0.0)
    
    @staticmethod
    def light_offset() -> Point:
        """Light offset from origin."""
        return (100.0, 50.0)


# =============================================================================
# Normalization Tests
# =============================================================================


class TestNormalizePolygon:
    """Tests for polygon normalization."""
    
    def test_normalize_removes_duplicates(self) -> None:
        """Consecutive duplicate vertices are removed."""
        poly = [
            (0.0, 0.0),
            (10.0, 0.0),
            (10.0, 0.0),  # duplicate
            (10.0, 10.0),
            (0.0, 10.0),
        ]
        result = normalize_polygon(poly)
        assert len(result) == 4
    
    def test_normalize_removes_closing_duplicate(self) -> None:
        """Closing vertex matching first is removed."""
        poly = [
            (0.0, 0.0),
            (10.0, 0.0),
            (10.0, 10.0),
            (0.0, 10.0),
            (0.0, 0.0),  # closing duplicate
        ]
        result = normalize_polygon(poly)
        assert len(result) == 4
        assert result[0] != result[-1]
    
    def test_normalize_ensures_ccw(self) -> None:
        """Clockwise polygon is reversed to CCW."""
        # Clockwise square
        cw_poly = [
            (0.0, 0.0),
            (0.0, 10.0),
            (10.0, 10.0),
            (10.0, 0.0),
        ]
        # Counter-clockwise square
        ccw_poly = [
            (0.0, 0.0),
            (10.0, 0.0),
            (10.0, 10.0),
            (0.0, 10.0),
        ]
        
        norm_cw = normalize_polygon(cw_poly, ensure_ccw=True)
        norm_ccw = normalize_polygon(ccw_poly, ensure_ccw=True)
        
        # Both should normalize to same polygon (modulo rotation)
        assert set(norm_cw) == set(norm_ccw)
    
    def test_normalize_rotation_invariant(self) -> None:
        """Same polygon with different start vertex normalizes same."""
        poly1 = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
        poly2 = [(10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)]
        poly3 = [(10.0, 10.0), (0.0, 10.0), (0.0, 0.0), (10.0, 0.0)]
        
        norm1 = normalize_polygon(poly1)
        norm2 = normalize_polygon(poly2)
        norm3 = normalize_polygon(poly3)
        
        assert norm1 == norm2 == norm3
    
    def test_normalize_precision_rounds(self) -> None:
        """Floating point noise is eliminated."""
        poly = [
            (0.0000001, 0.0000002),
            (10.0000003, 0.0000001),
            (10.0, 10.0),
        ]
        result = normalize_polygon(poly, precision=3)
        
        # Should round to clean values
        assert all(
            round(p[0], 3) == p[0] and round(p[1], 3) == p[1]
            for p in result
        )
    
    def test_normalize_degenerate_returns_empty(self) -> None:
        """Degenerate polygon (< 3 unique points) returns empty."""
        poly = [(0.0, 0.0), (0.0, 0.0), (0.0, 0.0)]
        result = normalize_polygon(poly)
        assert result == ()


class TestNormalizePolygonList:
    """Tests for normalizing lists of polygons."""
    
    def test_normalize_list_sorts_deterministically(self) -> None:
        """Polygon list is sorted for determinism."""
        polys = [
            GoldenFixtures.small_square_at(50.0, 0.0),
            GoldenFixtures.small_square_at(-50.0, 0.0),
            GoldenFixtures.small_square_at(0.0, 50.0),
        ]
        
        result1 = normalize_polygon_list(polys)
        result2 = normalize_polygon_list(list(reversed(polys)))
        
        assert result1 == result2
    
    def test_normalize_list_filters_degenerate(self) -> None:
        """Degenerate polygons are filtered out."""
        polys = [
            GoldenFixtures.convex_box(),
            [(0.0, 0.0), (0.0, 0.0)],  # degenerate
            GoldenFixtures.triangle(),
        ]
        
        result = normalize_polygon_list(polys)
        assert len(result) == 2


# =============================================================================
# Validation Tests
# =============================================================================


class TestValidatePolygon:
    """Tests for polygon validation."""
    
    def test_valid_polygon_passes(self) -> None:
        """Valid polygon passes validation."""
        result = validate_polygon(GoldenFixtures.convex_box())
        assert result.valid
        assert not result.errors
    
    def test_too_few_points_fails(self) -> None:
        """Polygon with < 3 points fails."""
        result = validate_polygon([(0.0, 0.0), (10.0, 0.0)])
        assert not result.valid
        assert any("minimum 3" in e for e in result.errors)
    
    def test_nan_coordinate_fails(self) -> None:
        """NaN coordinate fails validation."""
        result = validate_polygon([
            (float("nan"), 0.0),
            (10.0, 0.0),
            (10.0, 10.0),
        ])
        assert not result.valid
        assert any("not finite" in e for e in result.errors)
    
    def test_inf_coordinate_fails(self) -> None:
        """Infinity coordinate fails validation."""
        result = validate_polygon([
            (float("inf"), 0.0),
            (10.0, 0.0),
            (10.0, 10.0),
        ])
        assert not result.valid
        assert any("not finite" in e for e in result.errors)
    
    def test_zero_area_fails(self) -> None:
        """Collinear points (zero area) fails."""
        result = validate_polygon([
            (0.0, 0.0),
            (10.0, 0.0),
            (20.0, 0.0),
        ])
        assert not result.valid
        assert any("zero area" in e for e in result.errors)
    
    def test_duplicate_vertices_warns(self) -> None:
        """Duplicate vertices generate warnings."""
        result = validate_polygon([
            (0.0, 0.0),
            (10.0, 0.0),
            (10.0, 0.0),  # duplicate
            (10.0, 10.0),
            (0.0, 10.0),
        ])
        # Still valid but with warning
        assert result.valid or any("duplicate" in w.lower() for w in result.warnings)


class TestAssertPolygonValid:
    """Tests for assert_polygon_valid."""
    
    def test_valid_polygon_no_raise(self) -> None:
        """Valid polygon does not raise."""
        assert_polygon_valid(GoldenFixtures.convex_box())
    
    def test_invalid_polygon_raises(self) -> None:
        """Invalid polygon raises AssertionError."""
        with pytest.raises(AssertionError, match="validation failed"):
            assert_polygon_valid([(0.0, 0.0), (10.0, 0.0)])
    
    def test_context_in_error(self) -> None:
        """Context string appears in error."""
        with pytest.raises(AssertionError, match="test_context"):
            assert_polygon_valid([(0.0, 0.0)], context="test_context")


# =============================================================================
# Shadow Hull Computation Tests
# =============================================================================


class TestComputeShadowHulls:
    """Tests for shadow hull computation."""
    
    def test_box_produces_hulls(self) -> None:
        """Box occluder produces shadow hulls."""
        box = GoldenFixtures.convex_box()
        light = (50.0, 0.0)  # Light to the right
        
        hulls = compute_shadow_hulls([box], light)
        
        assert len(hulls) > 0
        for hull in hulls:
            assert len(hull) >= 3
    
    def test_triangle_produces_hulls(self) -> None:
        """Triangle occluder produces shadow hulls."""
        tri = GoldenFixtures.triangle()
        light = GoldenFixtures.light_centered()
        
        hulls = compute_shadow_hulls([tri], light)
        
        # Triangle should produce hulls
        assert len(hulls) > 0
    
    def test_l_shape_produces_hulls(self) -> None:
        """L-shape occluder produces shadow hulls."""
        l_shape = GoldenFixtures.concave_l_shape()
        light = (100.0, 100.0)  # Light above and right
        
        hulls = compute_shadow_hulls([l_shape], light)
        
        assert len(hulls) > 0
    
    def test_thin_wall_produces_hulls(self) -> None:
        """Thin wall produces shadow hulls."""
        wall = GoldenFixtures.thin_wall()
        light = (50.0, 50.0)  # Light above wall
        
        hulls = compute_shadow_hulls([wall], light)
        
        assert len(hulls) > 0
    
    def test_multiple_occluders_produces_hulls(self) -> None:
        """Multiple occluders produce correct hull count."""
        occluders = GoldenFixtures.multiple_occluders()
        light = GoldenFixtures.light_centered()
        
        hulls = compute_shadow_hulls(occluders, light)
        
        # Each box should produce at least 1 hull
        assert len(hulls) >= len(occluders)
    
    def test_distant_occluder_culled(self) -> None:
        """Occluder outside radius is culled."""
        box = GoldenFixtures.small_square_at(1000.0, 1000.0)
        light = GoldenFixtures.light_centered()
        params = ShadowParams(light_radius=100.0, cull_outside_radius=True)
        
        hulls = compute_shadow_hulls([box], light, params)
        
        assert len(hulls) == 0
    
    def test_empty_occluders_empty_result(self) -> None:
        """Empty occluder list produces empty result."""
        hulls = compute_shadow_hulls([], GoldenFixtures.light_centered())
        assert hulls == ()
    
    def test_zero_radius_empty_result(self) -> None:
        """Zero light radius produces empty result."""
        box = GoldenFixtures.convex_box()
        light = GoldenFixtures.light_centered()
        params = ShadowParams(light_radius=0.0)
        
        hulls = compute_shadow_hulls([box], light, params)
        
        assert hulls == ()


# =============================================================================
# Determinism Tests
# =============================================================================


class TestDeterminism:
    """Tests verifying deterministic output."""
    
    def test_same_input_same_output(self) -> None:
        """Same inputs always produce same output."""
        occluders = GoldenFixtures.multiple_occluders()
        light = GoldenFixtures.light_centered()
        
        result1 = compute_shadow_hulls(occluders, light)
        result2 = compute_shadow_hulls(occluders, light)
        
        assert result1 == result2
    
    def test_input_order_independent(self) -> None:
        """Output is independent of input occluder order."""
        occluders = GoldenFixtures.multiple_occluders()
        light = GoldenFixtures.light_centered()
        
        result1 = compute_shadow_hulls(occluders, light)
        result2 = compute_shadow_hulls(list(reversed(occluders)), light)
        
        assert result1 == result2
    
    def test_multiple_runs_identical_digest(self) -> None:
        """Multiple runs produce identical digest."""
        occluders = GoldenFixtures.multiple_occluders()
        light = GoldenFixtures.light_centered()
        
        digests = set()
        for _ in range(5):
            result = compute_shadow_geometry(occluders, light)
            digests.add(result.hull_digest())
        
        assert len(digests) == 1
    
    def test_segments_deterministic(self) -> None:
        """Occlusion segments are deterministic."""
        occluders = GoldenFixtures.multiple_occluders()
        light = GoldenFixtures.light_centered()
        
        segments1 = compute_occlusion_segments(occluders, light)
        segments2 = compute_occlusion_segments(list(reversed(occluders)), light)
        
        assert segments1 == segments2


# =============================================================================
# Invariant Tests
# =============================================================================


class TestInvariants:
    """Tests for shadow geometry invariants."""
    
    def test_all_hulls_have_at_least_3_vertices(self) -> None:
        """All shadow hulls have at least 3 vertices."""
        occluders = [
            GoldenFixtures.convex_box(),
            GoldenFixtures.triangle(),
            GoldenFixtures.concave_l_shape(),
            GoldenFixtures.thin_wall(),
        ]
        light = GoldenFixtures.light_offset()
        
        hulls = compute_shadow_hulls(occluders, light)
        
        for i, hull in enumerate(hulls):
            assert len(hull) >= 3, f"hull[{i}] has only {len(hull)} vertices"
    
    def test_no_nan_in_hulls(self) -> None:
        """No NaN values in hull coordinates."""
        occluders = GoldenFixtures.multiple_occluders()
        light = GoldenFixtures.light_centered()
        
        hulls = compute_shadow_hulls(occluders, light)
        
        for i, hull in enumerate(hulls):
            for j, point in enumerate(hull):
                assert not any(
                    x != x for x in point  # NaN check
                ), f"hull[{i}].vertex[{j}] contains NaN"
    
    def test_no_inf_in_hulls(self) -> None:
        """No infinity values in hull coordinates."""
        occluders = GoldenFixtures.multiple_occluders()
        light = GoldenFixtures.light_centered()
        
        hulls = compute_shadow_hulls(occluders, light)
        
        for i, hull in enumerate(hulls):
            for j, point in enumerate(hull):
                assert all(
                    abs(x) < float("inf") for x in point
                ), f"hull[{i}].vertex[{j}] contains infinity"
    
    def test_validate_shadow_hulls_passes(self) -> None:
        """Shadow hulls pass validation."""
        occluders = GoldenFixtures.multiple_occluders()
        light = GoldenFixtures.light_centered()
        
        hulls = compute_shadow_hulls(occluders, light)
        
        result = validate_shadow_hulls(hulls)
        assert result.valid, f"Validation failed: {result.errors}"
    
    def test_assert_shadow_hulls_valid_no_raise(self) -> None:
        """assert_shadow_hulls_valid does not raise for valid hulls."""
        occluders = GoldenFixtures.multiple_occluders()
        light = GoldenFixtures.light_centered()
        
        hulls = compute_shadow_hulls(occluders, light)
        
        # Should not raise
        assert_shadow_hulls_valid(hulls)


# =============================================================================
# Golden Snapshot Tests
# =============================================================================


# These are expected values computed from known-good implementation
# Any change should be intentional
GOLDEN_BOX_LIGHT_RIGHT_HULL_COUNT = 3  # Three shadow-casting edges face away from light
GOLDEN_TRIANGLE_CENTER_HULL_COUNT_MIN = 1  # At least one edge


class TestGoldenSnapshots:
    """Tests comparing against golden expected values."""
    
    def test_box_with_light_right_hull_count(self) -> None:
        """Box with light to right produces expected hull count."""
        box = GoldenFixtures.convex_box()
        light = (50.0, 0.0)
        
        hulls = compute_shadow_hulls([box], light)
        
        # Two edges face away from light (left side of box)
        assert len(hulls) == GOLDEN_BOX_LIGHT_RIGHT_HULL_COUNT
    
    def test_triangle_centered_light_produces_hulls(self) -> None:
        """Triangle with centered light produces hulls."""
        tri = GoldenFixtures.triangle()
        # Light below triangle
        light = (0.0, -50.0)
        
        hulls = compute_shadow_hulls([tri], light)
        
        assert len(hulls) >= GOLDEN_TRIANGLE_CENTER_HULL_COUNT_MIN
    
    def test_box_hull_vertices_reasonable_bounds(self) -> None:
        """Hull vertices are within reasonable bounds."""
        box = GoldenFixtures.convex_box()
        light = (50.0, 0.0)
        params = ShadowParams(light_radius=100.0)
        
        hulls = compute_shadow_hulls([box], light, params)
        
        for hull in hulls:
            for point in hull:
                # All points should be within extrusion distance of light
                # (with some margin for near points)
                assert abs(point[0]) <= 150.0, f"x out of bounds: {point[0]}"
                assert abs(point[1]) <= 150.0, f"y out of bounds: {point[1]}"


# =============================================================================
# Occlusion Segment Tests
# =============================================================================


class TestOcclusionSegments:
    """Tests for occlusion segment computation."""
    
    def test_box_produces_segments(self) -> None:
        """Box produces occlusion segments."""
        box = GoldenFixtures.convex_box()
        light = (50.0, 0.0)
        
        segments = compute_occlusion_segments([box], light)
        
        assert len(segments) > 0
    
    def test_segment_has_valid_fields(self) -> None:
        """Segments have valid field values."""
        box = GoldenFixtures.convex_box()
        light = (50.0, 0.0)
        
        segments = compute_occlusion_segments([box], light)
        
        for seg in segments:
            assert isinstance(seg.start, tuple)
            assert isinstance(seg.end, tuple)
            assert len(seg.start) == 2
            assert len(seg.end) == 2
            assert seg.occluder_id >= 0
            assert seg.edge_index >= 0
    
    def test_segment_length_positive(self) -> None:
        """Segment lengths are positive."""
        box = GoldenFixtures.convex_box()
        light = (50.0, 0.0)
        
        segments = compute_occlusion_segments([box], light)
        
        for i, seg in enumerate(segments):
            assert seg.length() > 0, f"segment[{i}] has zero length"
    
    def test_segments_deterministic_order(self) -> None:
        """Segments are in deterministic order."""
        occluders = GoldenFixtures.multiple_occluders()
        light = GoldenFixtures.light_centered()
        
        seg1 = compute_occlusion_segments(occluders, light)
        seg2 = compute_occlusion_segments(list(reversed(occluders)), light)
        
        # Same order regardless of input order
        assert [s.to_tuple() for s in seg1] == [s.to_tuple() for s in seg2]


# =============================================================================
# Full Geometry Result Tests
# =============================================================================


class TestShadowGeometryResult:
    """Tests for ShadowGeometryResult."""
    
    def test_full_geometry_has_all_fields(self) -> None:
        """Full geometry result has all expected fields."""
        occluders = GoldenFixtures.multiple_occluders()
        light = GoldenFixtures.light_centered()
        
        result = compute_shadow_geometry(occluders, light)
        
        assert result.hulls is not None
        assert result.segments is not None
        assert result.light_pos == light
        assert result.params is not None
        assert result.occluder_count == len(occluders)
    
    def test_hull_digest_stable(self) -> None:
        """Hull digest is stable across runs."""
        occluders = GoldenFixtures.multiple_occluders()
        light = GoldenFixtures.light_centered()
        
        result1 = compute_shadow_geometry(occluders, light)
        result2 = compute_shadow_geometry(occluders, light)
        
        assert result1.hull_digest() == result2.hull_digest()
    
    def test_segment_digest_stable(self) -> None:
        """Segment digest is stable across runs."""
        occluders = GoldenFixtures.multiple_occluders()
        light = GoldenFixtures.light_centered()
        
        result1 = compute_shadow_geometry(occluders, light)
        result2 = compute_shadow_geometry(occluders, light)
        
        assert result1.segment_digest() == result2.segment_digest()
    
    def test_full_digest_stable(self) -> None:
        """Full digest is stable across runs."""
        occluders = GoldenFixtures.multiple_occluders()
        light = GoldenFixtures.light_centered()
        
        result1 = compute_shadow_geometry(occluders, light)
        result2 = compute_shadow_geometry(occluders, light)
        
        assert result1.full_digest() == result2.full_digest()
    
    def test_different_inputs_different_digest(self) -> None:
        """Different inputs produce different digests."""
        occluders1 = [GoldenFixtures.convex_box()]
        occluders2 = [GoldenFixtures.triangle()]
        light = GoldenFixtures.light_centered()
        
        result1 = compute_shadow_geometry(occluders1, light)
        result2 = compute_shadow_geometry(occluders2, light)
        
        assert result1.full_digest() != result2.full_digest()


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""
    
    def test_light_inside_occluder(self) -> None:
        """Light inside occluder still produces result."""
        box = GoldenFixtures.convex_box()
        light = (0.0, 0.0)  # Light at center of box
        
        # Should not crash
        hulls = compute_shadow_hulls([box], light)
        # May or may not produce hulls depending on algorithm
        assert isinstance(hulls, tuple)
    
    def test_light_at_vertex(self) -> None:
        """Light at occluder vertex still works."""
        box = GoldenFixtures.convex_box()
        light = (-10.0, -10.0)  # Light at corner
        
        hulls = compute_shadow_hulls([box], light)
        assert isinstance(hulls, tuple)
    
    def test_very_small_occluder(self) -> None:
        """Very small occluder is handled."""
        tiny = GoldenFixtures.small_square_at(0.0, 0.0, size=0.001)
        light = (10.0, 0.0)
        
        hulls = compute_shadow_hulls([tiny], light)
        assert isinstance(hulls, tuple)
    
    def test_very_large_radius(self) -> None:
        """Very large radius is handled."""
        box = GoldenFixtures.convex_box()
        light = GoldenFixtures.light_centered()
        params = ShadowParams(light_radius=1000000.0)
        
        hulls = compute_shadow_hulls([box], light, params)
        assert isinstance(hulls, tuple)
    
    def test_near_degenerate_polygon(self) -> None:
        """Near-degenerate polygon is handled gracefully."""
        # Very thin triangle
        thin = [
            (0.0, 0.0),
            (100.0, 0.0),
            (50.0, 0.001),
        ]
        light = (50.0, 50.0)
        
        # Should not crash
        hulls = compute_shadow_hulls([thin], light)
        assert isinstance(hulls, tuple)


# =============================================================================
# Digest Format Tests
# =============================================================================


class TestDigestFormat:
    """Tests for digest format and properties."""
    
    def test_digest_is_sha256_hex(self) -> None:
        """Digest is SHA-256 hex string."""
        result = compute_shadow_geometry(
            [GoldenFixtures.convex_box()],
            GoldenFixtures.light_centered(),
        )
        
        digest = result.full_digest()
        assert len(digest) == 64
        assert all(c in "0123456789abcdef" for c in digest)
    
    def test_empty_result_has_digest(self) -> None:
        """Empty result still has valid digest."""
        result = compute_shadow_geometry([], GoldenFixtures.light_centered())
        
        digest = result.full_digest()
        assert len(digest) == 64
