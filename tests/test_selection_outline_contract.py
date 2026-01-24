"""Contract tests for selection_outline pure module.

Tests selection outline computation as pure functions - headless, no arcade dependency.
"""

from __future__ import annotations

import pytest

from engine.editor.selection_outline import (
    RectF,
    SelectionOutline,
    GroupBounds,
    resolve_entity_bounds,
    build_selection_outlines,
    compute_group_bounds,
    rect_to_border_segments,
    rect_to_corner_markers,
)


# -----------------------------------------------------------------------------
# RectF
# -----------------------------------------------------------------------------


class TestRectF:
    """Tests for RectF dataclass."""

    def test_creation(self) -> None:
        rect = RectF(x=10.0, y=20.0, w=100.0, h=50.0)
        assert rect.x == 10.0
        assert rect.y == 20.0
        assert rect.w == 100.0
        assert rect.h == 50.0

    def test_left_right_edges(self) -> None:
        rect = RectF(x=10.0, y=20.0, w=100.0, h=50.0)
        assert rect.left == 10.0
        assert rect.right == 110.0

    def test_bottom_top_edges(self) -> None:
        rect = RectF(x=10.0, y=20.0, w=100.0, h=50.0)
        assert rect.bottom == 20.0
        assert rect.top == 70.0

    def test_center(self) -> None:
        rect = RectF(x=10.0, y=20.0, w=100.0, h=50.0)
        assert rect.center_x == 60.0
        assert rect.center_y == 45.0

    def test_contains_point_inside(self) -> None:
        rect = RectF(x=0.0, y=0.0, w=100.0, h=100.0)
        assert rect.contains_point(50.0, 50.0) is True

    def test_contains_point_on_edge(self) -> None:
        rect = RectF(x=0.0, y=0.0, w=100.0, h=100.0)
        assert rect.contains_point(0.0, 50.0) is True
        assert rect.contains_point(100.0, 50.0) is True

    def test_contains_point_outside(self) -> None:
        rect = RectF(x=0.0, y=0.0, w=100.0, h=100.0)
        assert rect.contains_point(-1.0, 50.0) is False
        assert rect.contains_point(101.0, 50.0) is False
        assert rect.contains_point(50.0, -1.0) is False
        assert rect.contains_point(50.0, 101.0) is False


# -----------------------------------------------------------------------------
# resolve_entity_bounds
# -----------------------------------------------------------------------------


class TestResolveEntityBounds:
    """Tests for resolve_entity_bounds function."""

    def test_from_sprite_with_full_data(self) -> None:
        class MockSprite:
            center_x = 100.0
            center_y = 200.0
            width = 64.0
            height = 32.0

        result = resolve_entity_bounds({}, MockSprite())
        assert result is not None
        assert result.center_x == pytest.approx(100.0)
        assert result.center_y == pytest.approx(200.0)
        assert result.w == 64.0
        assert result.h == 32.0

    def test_from_entity_data_with_width_height(self) -> None:
        entity_data = {"x": 100.0, "y": 200.0, "width": 48.0, "height": 24.0}
        result = resolve_entity_bounds(entity_data, None)
        assert result is not None
        assert result.center_x == pytest.approx(100.0)
        assert result.center_y == pytest.approx(200.0)
        assert result.w == 48.0
        assert result.h == 24.0

    def test_from_entity_data_with_w_h(self) -> None:
        entity_data = {"x": 50.0, "y": 75.0, "w": 32.0, "h": 16.0}
        result = resolve_entity_bounds(entity_data, None)
        assert result is not None
        assert result.w == 32.0
        assert result.h == 16.0

    def test_fallback_to_default_size(self) -> None:
        entity_data = {"x": 100.0, "y": 100.0}
        result = resolve_entity_bounds(entity_data, None)
        assert result is not None
        assert result.w == 32.0  # Default size
        assert result.h == 32.0

    def test_sprite_takes_precedence(self) -> None:
        class MockSprite:
            center_x = 50.0
            center_y = 50.0
            width = 20.0
            height = 20.0

        entity_data = {"x": 100.0, "y": 100.0, "width": 64.0, "height": 64.0}
        result = resolve_entity_bounds(entity_data, MockSprite())
        assert result is not None
        # Sprite values should be used
        assert result.center_x == pytest.approx(50.0)
        assert result.w == 20.0

    def test_returns_none_for_missing_position(self) -> None:
        entity_data = {"width": 32.0, "height": 32.0}
        result = resolve_entity_bounds(entity_data, None)
        assert result is None

    def test_handles_invalid_entity_data(self) -> None:
        result = resolve_entity_bounds("not a dict", None)  # type: ignore
        assert result is None


# -----------------------------------------------------------------------------
# build_selection_outlines
# -----------------------------------------------------------------------------


class TestBuildSelectionOutlines:
    """Tests for build_selection_outlines function."""

    def test_single_selection(self) -> None:
        entity_by_id = {"ent_1": {"x": 100.0, "y": 100.0, "width": 32.0, "height": 32.0}}
        sprite_by_id: dict = {}

        outlines = build_selection_outlines(
            selected_ids=["ent_1"],
            primary_id="ent_1",
            entity_by_id=entity_by_id,
            sprite_by_id=sprite_by_id,
        )

        assert len(outlines) == 1
        assert outlines[0].entity_id == "ent_1"
        assert outlines[0].is_primary is True

    def test_multi_selection_ordering(self) -> None:
        entity_by_id = {
            "ent_a": {"x": 0.0, "y": 0.0},
            "ent_b": {"x": 100.0, "y": 0.0},
            "ent_c": {"x": 200.0, "y": 0.0},
        }
        sprite_by_id: dict = {}

        outlines = build_selection_outlines(
            selected_ids=["ent_c", "ent_a", "ent_b"],
            primary_id="ent_a",
            entity_by_id=entity_by_id,
            sprite_by_id=sprite_by_id,
        )

        # Order should match selected_ids
        assert len(outlines) == 3
        assert outlines[0].entity_id == "ent_c"
        assert outlines[1].entity_id == "ent_a"
        assert outlines[2].entity_id == "ent_b"

    def test_primary_flag(self) -> None:
        entity_by_id = {
            "ent_a": {"x": 0.0, "y": 0.0},
            "ent_b": {"x": 100.0, "y": 0.0},
        }
        sprite_by_id: dict = {}

        outlines = build_selection_outlines(
            selected_ids=["ent_a", "ent_b"],
            primary_id="ent_b",
            entity_by_id=entity_by_id,
            sprite_by_id=sprite_by_id,
        )

        assert outlines[0].is_primary is False
        assert outlines[1].is_primary is True

    def test_skips_entities_without_bounds(self) -> None:
        entity_by_id = {
            "ent_good": {"x": 0.0, "y": 0.0},
            "ent_bad": {},  # No position
        }
        sprite_by_id: dict = {}

        outlines = build_selection_outlines(
            selected_ids=["ent_good", "ent_bad"],
            primary_id=None,
            entity_by_id=entity_by_id,
            sprite_by_id=sprite_by_id,
        )

        assert len(outlines) == 1
        assert outlines[0].entity_id == "ent_good"

    def test_empty_selection(self) -> None:
        outlines = build_selection_outlines(
            selected_ids=[],
            primary_id=None,
            entity_by_id={},
            sprite_by_id={},
        )
        assert outlines == []

    def test_uses_sprite_for_bounds(self) -> None:
        class MockSprite:
            center_x = 50.0
            center_y = 50.0
            width = 64.0
            height = 64.0

        entity_by_id = {"ent_1": {"x": 0.0, "y": 0.0}}  # Different position
        sprite_by_id = {"ent_1": MockSprite()}

        outlines = build_selection_outlines(
            selected_ids=["ent_1"],
            primary_id=None,
            entity_by_id=entity_by_id,
            sprite_by_id=sprite_by_id,
        )

        assert len(outlines) == 1
        # Should use sprite position
        assert outlines[0].rect.center_x == pytest.approx(50.0)


# -----------------------------------------------------------------------------
# compute_group_bounds
# -----------------------------------------------------------------------------


class TestComputeGroupBounds:
    """Tests for compute_group_bounds function."""

    def test_returns_none_for_single_outline(self) -> None:
        outline = SelectionOutline(
            entity_id="ent_1",
            rect=RectF(x=0.0, y=0.0, w=32.0, h=32.0),
            is_primary=True,
        )
        result = compute_group_bounds([outline])
        assert result is None

    def test_returns_none_for_empty(self) -> None:
        result = compute_group_bounds([])
        assert result is None

    def test_aabb_union_two_outlines(self) -> None:
        outline1 = SelectionOutline(
            entity_id="ent_1",
            rect=RectF(x=0.0, y=0.0, w=32.0, h=32.0),
            is_primary=False,
        )
        outline2 = SelectionOutline(
            entity_id="ent_2",
            rect=RectF(x=100.0, y=50.0, w=32.0, h=32.0),
            is_primary=False,
        )

        result = compute_group_bounds([outline1, outline2])
        assert result is not None

        # Union should span from (0,0) to (132, 82)
        assert result.rect.left == pytest.approx(0.0)
        assert result.rect.bottom == pytest.approx(0.0)
        assert result.rect.right == pytest.approx(132.0)
        assert result.rect.top == pytest.approx(82.0)

    def test_aabb_union_three_outlines(self) -> None:
        outlines = [
            SelectionOutline("a", RectF(x=0.0, y=0.0, w=10.0, h=10.0), False),
            SelectionOutline("b", RectF(x=50.0, y=50.0, w=10.0, h=10.0), False),
            SelectionOutline("c", RectF(x=-20.0, y=30.0, w=10.0, h=10.0), True),
        ]

        result = compute_group_bounds(outlines)
        assert result is not None

        # Min x = -20, Max x = 60, Min y = 0, Max y = 60
        assert result.rect.left == pytest.approx(-20.0)
        assert result.rect.right == pytest.approx(60.0)
        assert result.rect.bottom == pytest.approx(0.0)
        assert result.rect.top == pytest.approx(60.0)


# -----------------------------------------------------------------------------
# rect_to_border_segments
# -----------------------------------------------------------------------------


class TestRectToBorderSegments:
    """Tests for rect_to_border_segments function."""

    def test_returns_four_segments(self) -> None:
        rect = RectF(x=0.0, y=0.0, w=100.0, h=50.0)
        segments = rect_to_border_segments(rect)
        assert len(segments) == 4

    def test_segment_coordinates(self) -> None:
        rect = RectF(x=10.0, y=20.0, w=100.0, h=50.0)
        top, right, bottom, left = rect_to_border_segments(rect)

        # Top: (10, 70) to (110, 70)
        assert top == (10.0, 70.0, 110.0, 70.0)

        # Right: (110, 70) to (110, 20)
        assert right == (110.0, 70.0, 110.0, 20.0)

        # Bottom: (110, 20) to (10, 20)
        assert bottom == (110.0, 20.0, 10.0, 20.0)

        # Left: (10, 20) to (10, 70)
        assert left == (10.0, 20.0, 10.0, 70.0)

    def test_unit_square(self) -> None:
        rect = RectF(x=0.0, y=0.0, w=1.0, h=1.0)
        top, right, bottom, left = rect_to_border_segments(rect)

        assert top == (0.0, 1.0, 1.0, 1.0)
        assert right == (1.0, 1.0, 1.0, 0.0)
        assert bottom == (1.0, 0.0, 0.0, 0.0)
        assert left == (0.0, 0.0, 0.0, 1.0)


# -----------------------------------------------------------------------------
# rect_to_corner_markers
# -----------------------------------------------------------------------------


class TestRectToCornerMarkers:
    """Tests for rect_to_corner_markers function."""

    def test_returns_four_corners(self) -> None:
        rect = RectF(x=0.0, y=0.0, w=100.0, h=100.0)
        corners = rect_to_corner_markers(rect, marker_size=10.0)
        assert len(corners) == 4

    def test_each_corner_has_two_segments(self) -> None:
        rect = RectF(x=0.0, y=0.0, w=100.0, h=100.0)
        corners = rect_to_corner_markers(rect, marker_size=10.0)

        for h_seg, v_seg in corners:
            # Each segment should be a tuple of 4 floats
            assert len(h_seg) == 4
            assert len(v_seg) == 4

    def test_marker_size_affects_segments(self) -> None:
        rect = RectF(x=0.0, y=0.0, w=100.0, h=100.0)
        corners_small = rect_to_corner_markers(rect, marker_size=5.0)
        corners_large = rect_to_corner_markers(rect, marker_size=20.0)

        # Top-left horizontal segment length should differ
        h_small = corners_small[0][0]
        h_large = corners_large[0][0]

        # x2 - x1 = marker_size
        assert abs(h_small[2] - h_small[0]) == pytest.approx(5.0)
        assert abs(h_large[2] - h_large[0]) == pytest.approx(20.0)


# -----------------------------------------------------------------------------
# SelectionOutline dataclass
# -----------------------------------------------------------------------------


class TestSelectionOutline:
    """Tests for SelectionOutline dataclass."""

    def test_creation(self) -> None:
        rect = RectF(x=0.0, y=0.0, w=32.0, h=32.0)
        outline = SelectionOutline(entity_id="test_entity", rect=rect, is_primary=True)

        assert outline.entity_id == "test_entity"
        assert outline.rect == rect
        assert outline.is_primary is True


# -----------------------------------------------------------------------------
# GroupBounds dataclass
# -----------------------------------------------------------------------------


class TestGroupBounds:
    """Tests for GroupBounds dataclass."""

    def test_creation(self) -> None:
        rect = RectF(x=0.0, y=0.0, w=200.0, h=150.0)
        bounds = GroupBounds(rect=rect)

        assert bounds.rect == rect
        assert bounds.rect.w == 200.0
