"""Contract tests for parallax_model.py.

Tests cover:
- compute_parallax_offset determinism
- BackgroundPlane dataclass defaults
- parse_background_planes from scene payload
- sort_background_planes ordering
- background_planes_to_payloads roundtrip
"""

from __future__ import annotations

import pytest

from engine.parallax_model import (
    BackgroundPlane,
    compute_parallax_offset,
    compute_parallax_offset_with_zoom,
    parse_background_planes,
    sort_background_planes,
    background_planes_to_payloads,
)


# -----------------------------------------------------------------------------
# Test compute_parallax_offset
# -----------------------------------------------------------------------------


class TestComputeParallaxOffset:
    """Tests for compute_parallax_offset function."""

    def test_zero_parallax_no_movement(self) -> None:
        """parallax=0 should produce no offset (fixed to screen)."""
        dx, dy = compute_parallax_offset(100.0, 200.0, parallax=0.0)
        assert dx == 0.0
        assert dy == 0.0

    def test_full_parallax_moves_with_camera(self) -> None:
        """parallax=1 should move opposite to camera."""
        dx, dy = compute_parallax_offset(100.0, 50.0, parallax=1.0)
        assert dx == -100.0
        assert dy == -50.0

    def test_half_parallax_half_speed(self) -> None:
        """parallax=0.5 should move at half the speed."""
        dx, dy = compute_parallax_offset(100.0, 50.0, parallax=0.5)
        assert dx == -50.0
        assert dy == -25.0

    def test_deterministic_same_inputs(self) -> None:
        """Same inputs should produce same outputs."""
        result1 = compute_parallax_offset(123.456, 789.012, parallax=0.7)
        result2 = compute_parallax_offset(123.456, 789.012, parallax=0.7)
        assert result1 == result2


class TestComputeParallaxOffsetWithZoom:
    """Tests for compute_parallax_offset_with_zoom function."""

    def test_zoom_1_same_as_no_zoom(self) -> None:
        """zoom=1 should produce same result as compute_parallax_offset."""
        result1 = compute_parallax_offset(100.0, 50.0, parallax=0.5)
        result2 = compute_parallax_offset_with_zoom(100.0, 50.0, parallax=0.5, zoom=1.0)
        assert result1 == result2

    def test_zoom_2_doubles_offset(self) -> None:
        """zoom=2 should double the offset."""
        dx, dy = compute_parallax_offset_with_zoom(100.0, 50.0, parallax=0.5, zoom=2.0)
        assert dx == -100.0  # -100 * 0.5 * 2
        assert dy == -50.0   # -50 * 0.5 * 2


# -----------------------------------------------------------------------------
# Test BackgroundPlane dataclass
# -----------------------------------------------------------------------------


class TestBackgroundPlane:
    """Tests for BackgroundPlane dataclass."""

    def test_default_values(self) -> None:
        """BackgroundPlane should have sensible defaults."""
        plane = BackgroundPlane(asset_path="bg.png")
        assert plane.asset_path == "bg.png"
        assert plane.parallax == 0.5
        assert plane.render_layer == 0
        assert plane.alpha == 1.0
        assert plane.tint is None
        assert plane.offset_x == 0.0
        assert plane.offset_y == 0.0
        assert plane.repeat_x is False
        assert plane.repeat_y is False
        assert plane.id == ""

    def test_custom_values(self) -> None:
        """BackgroundPlane should accept custom values."""
        plane = BackgroundPlane(
            asset_path="sky.png",
            parallax=0.2,
            render_layer=-5,
            alpha=0.8,
            tint=(255, 200, 150, 200),
            offset_x=10.0,
            offset_y=-20.0,
            repeat_x=True,
            repeat_y=False,
            id="sky_layer",
        )
        assert plane.parallax == 0.2
        assert plane.render_layer == -5
        assert plane.alpha == 0.8
        assert plane.tint == (255, 200, 150, 200)
        assert plane.offset_x == 10.0
        assert plane.offset_y == -20.0
        assert plane.repeat_x is True
        assert plane.repeat_y is False
        assert plane.id == "sky_layer"

    def test_immutable(self) -> None:
        """BackgroundPlane should be frozen (immutable)."""
        plane = BackgroundPlane(asset_path="bg.png")
        with pytest.raises(AttributeError):
            plane.asset_path = "other.png"  # type: ignore


# -----------------------------------------------------------------------------
# Test parse_background_planes
# -----------------------------------------------------------------------------


class TestParseBackgroundPlanes:
    """Tests for parse_background_planes function."""

    def test_missing_key_returns_empty(self) -> None:
        """Missing background_planes key should return empty list."""
        result = parse_background_planes({})
        assert result == []

    def test_none_value_returns_empty(self) -> None:
        """None value for background_planes should return empty list."""
        result = parse_background_planes({"background_planes": None})
        assert result == []

    def test_non_list_returns_empty(self) -> None:
        """Non-list value should return empty list."""
        result = parse_background_planes({"background_planes": "invalid"})
        assert result == []

    def test_parses_valid_plane(self) -> None:
        """Valid plane should be parsed correctly."""
        payload = {
            "background_planes": [
                {
                    "id": "sky",
                    "asset_path": "assets/sky.png",
                    "parallax": 0.3,
                    "render_layer": -10,
                }
            ]
        }
        result = parse_background_planes(payload)
        assert len(result) == 1
        assert result[0].id == "sky"
        assert result[0].asset_path == "assets/sky.png"
        assert result[0].parallax == 0.3
        assert result[0].render_layer == -10

    def test_skips_invalid_entries(self) -> None:
        """Invalid entries should be skipped."""
        payload = {
            "background_planes": [
                {"id": "valid", "asset_path": "bg.png"},
                {"id": "no_path"},  # Missing asset_path
                "not_a_dict",
                {"asset_path": "no_id.png"},  # ID will be auto-generated
            ]
        }
        result = parse_background_planes(payload)
        assert len(result) == 2
        assert result[0].id == "plane_3"  # Auto-generated for entry at index 3
        assert result[1].id == "valid"

    def test_parallax_clamped(self) -> None:
        """Parallax should be clamped to [0.0, 2.0]."""
        payload = {
            "background_planes": [
                {"id": "low", "asset_path": "bg.png", "parallax": -1.0},
                {"id": "high", "asset_path": "bg.png", "parallax": 5.0},
            ]
        }
        result = parse_background_planes(payload)
        # Sorted by render_layer (both 0), then by id: "high" < "low"
        assert result[0].id == "high"
        assert result[0].parallax == 2.0  # Clamped from 5.0
        assert result[1].id == "low"
        assert result[1].parallax == 0.0  # Clamped from -1.0

    def test_alpha_clamped(self) -> None:
        """Alpha should be clamped to [0.0, 1.0]."""
        payload = {
            "background_planes": [
                {"id": "low", "asset_path": "bg.png", "alpha": -0.5},
                {"id": "high", "asset_path": "bg.png", "alpha": 2.0},
            ]
        }
        result = parse_background_planes(payload)
        # Sorted by render_layer (both 0), then by id: "high" < "low"
        assert result[0].id == "high"
        assert result[0].alpha == 1.0  # Clamped from 2.0
        assert result[1].id == "low"
        assert result[1].alpha == 0.0  # Clamped from -0.5

    def test_sorted_by_render_layer(self) -> None:
        """Result should be sorted by render_layer."""
        payload = {
            "background_planes": [
                {"id": "mid", "asset_path": "bg.png", "render_layer": 0},
                {"id": "back", "asset_path": "bg.png", "render_layer": -5},
                {"id": "front", "asset_path": "bg.png", "render_layer": 5},
            ]
        }
        result = parse_background_planes(payload)
        assert [p.id for p in result] == ["back", "mid", "front"]


# -----------------------------------------------------------------------------
# Test sort_background_planes
# -----------------------------------------------------------------------------


class TestSortBackgroundPlanes:
    """Tests for sort_background_planes function."""

    def test_sort_by_render_layer(self) -> None:
        """Planes should be sorted by render_layer ascending."""
        planes = [
            BackgroundPlane(asset_path="a.png", render_layer=5, id="a"),
            BackgroundPlane(asset_path="b.png", render_layer=-5, id="b"),
            BackgroundPlane(asset_path="c.png", render_layer=0, id="c"),
        ]
        result = sort_background_planes(planes)
        assert [p.id for p in result] == ["b", "c", "a"]

    def test_tie_break_by_id(self) -> None:
        """Same render_layer should tie-break by id."""
        planes = [
            BackgroundPlane(asset_path="a.png", render_layer=0, id="charlie"),
            BackgroundPlane(asset_path="b.png", render_layer=0, id="alpha"),
            BackgroundPlane(asset_path="c.png", render_layer=0, id="bravo"),
        ]
        result = sort_background_planes(planes)
        assert [p.id for p in result] == ["alpha", "bravo", "charlie"]


# -----------------------------------------------------------------------------
# Test roundtrip
# -----------------------------------------------------------------------------


class TestBackgroundPlanesRoundtrip:
    """Tests for background_planes_to_payloads function."""

    def test_basic_roundtrip(self) -> None:
        """Planes should survive a to_payloads -> parse roundtrip."""
        original = [
            BackgroundPlane(
                asset_path="sky.png",
                parallax=0.3,
                render_layer=-10,
                id="sky",
            ),
            BackgroundPlane(
                asset_path="mountains.png",
                parallax=0.5,
                render_layer=-5,
                alpha=0.9,
                id="mountains",
            ),
        ]
        payloads = background_planes_to_payloads(original)
        parsed = parse_background_planes({"background_planes": payloads})

        assert len(parsed) == 2
        # Sorted by render_layer, so sky (-10) comes first
        assert parsed[0].id == "sky"
        assert parsed[0].asset_path == "sky.png"
        assert parsed[0].parallax == 0.3
        assert parsed[1].id == "mountains"
        assert parsed[1].alpha == 0.9

    def test_sparse_payload_omits_defaults(self) -> None:
        """Payload should omit fields that have default values."""
        plane = BackgroundPlane(
            asset_path="bg.png",
            parallax=0.5,
            render_layer=0,
            id="bg",
        )
        payloads = background_planes_to_payloads([plane])
        payload = payloads[0]
        # alpha=1.0 is default, should not be in payload
        assert "alpha" not in payload
        assert "offset_x" not in payload
        assert "repeat_x" not in payload
