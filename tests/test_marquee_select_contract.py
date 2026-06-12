"""Contract tests for marquee_select pure module.

Tests marquee selection computation as pure functions - headless, no arcade dependency.
"""

from __future__ import annotations

import pytest

from engine.editor.marquee_select import (
    MarqueeState,
    apply_marquee_selection,
    compute_marquee_candidates,
    get_marquee_rect_from_state,
    rect_from_points,
    rect_intersects,
    should_start_marquee,
)
from engine.editor.selection_outline import RectF
from tests._typing import as_any

# -----------------------------------------------------------------------------
# rect_from_points
# -----------------------------------------------------------------------------


class TestRectFromPoints:
    """Tests for rect_from_points function."""

    def test_normalized_from_top_left_to_bottom_right(self) -> None:
        rect = rect_from_points((0.0, 100.0), (100.0, 0.0))
        assert rect.x == 0.0
        assert rect.y == 0.0
        assert rect.w == 100.0
        assert rect.h == 100.0

    def test_normalized_from_bottom_left_to_top_right(self) -> None:
        rect = rect_from_points((0.0, 0.0), (100.0, 100.0))
        assert rect.x == 0.0
        assert rect.y == 0.0
        assert rect.w == 100.0
        assert rect.h == 100.0

    def test_normalized_from_bottom_right_to_top_left(self) -> None:
        rect = rect_from_points((100.0, 0.0), (0.0, 100.0))
        assert rect.left == 0.0
        assert rect.bottom == 0.0
        assert rect.right == 100.0
        assert rect.top == 100.0

    def test_zero_size_rect(self) -> None:
        rect = rect_from_points((50.0, 50.0), (50.0, 50.0))
        assert rect.w == 0.0
        assert rect.h == 0.0

    def test_negative_coordinates(self) -> None:
        rect = rect_from_points((-50.0, -50.0), (50.0, 50.0))
        assert rect.left == -50.0
        assert rect.bottom == -50.0
        assert rect.right == 50.0
        assert rect.top == 50.0


# -----------------------------------------------------------------------------
# rect_intersects
# -----------------------------------------------------------------------------


class TestRectIntersects:
    """Tests for rect_intersects function."""

    def test_overlapping_rects(self) -> None:
        a = RectF(x=0.0, y=0.0, w=50.0, h=50.0)
        b = RectF(x=25.0, y=25.0, w=50.0, h=50.0)
        assert rect_intersects(a, b) is True
        assert rect_intersects(b, a) is True

    def test_touching_edges(self) -> None:
        a = RectF(x=0.0, y=0.0, w=50.0, h=50.0)
        b = RectF(x=50.0, y=0.0, w=50.0, h=50.0)
        # Touching at edge is considered intersection
        assert rect_intersects(a, b) is True

    def test_no_intersection_horizontal(self) -> None:
        a = RectF(x=0.0, y=0.0, w=50.0, h=50.0)
        b = RectF(x=100.0, y=0.0, w=50.0, h=50.0)
        assert rect_intersects(a, b) is False

    def test_no_intersection_vertical(self) -> None:
        a = RectF(x=0.0, y=0.0, w=50.0, h=50.0)
        b = RectF(x=0.0, y=100.0, w=50.0, h=50.0)
        assert rect_intersects(a, b) is False

    def test_one_contains_other(self) -> None:
        outer = RectF(x=0.0, y=0.0, w=100.0, h=100.0)
        inner = RectF(x=25.0, y=25.0, w=50.0, h=50.0)
        assert rect_intersects(outer, inner) is True
        assert rect_intersects(inner, outer) is True


# -----------------------------------------------------------------------------
# compute_marquee_candidates
# -----------------------------------------------------------------------------


class TestComputeMarqueeCandidates:
    """Tests for compute_marquee_candidates function."""

    def test_returns_intersecting_entities(self) -> None:
        marquee = RectF(x=0.0, y=0.0, w=50.0, h=50.0)
        entity_bounds = [
            ("ent_a", RectF(x=10.0, y=10.0, w=20.0, h=20.0)),
            ("ent_b", RectF(x=100.0, y=100.0, w=20.0, h=20.0)),
            ("ent_c", RectF(x=40.0, y=40.0, w=20.0, h=20.0)),
        ]
        result = compute_marquee_candidates(marquee, entity_bounds)
        assert "ent_a" in result
        assert "ent_c" in result
        assert "ent_b" not in result

    def test_empty_on_no_intersection(self) -> None:
        marquee = RectF(x=0.0, y=0.0, w=10.0, h=10.0)
        entity_bounds = [
            ("ent_a", RectF(x=100.0, y=100.0, w=20.0, h=20.0)),
        ]
        result = compute_marquee_candidates(marquee, entity_bounds)
        assert result == []

    def test_deterministic_ordering(self) -> None:
        marquee = RectF(x=0.0, y=0.0, w=100.0, h=100.0)
        # Entities in unsorted order
        entity_bounds = [
            ("ent_z", RectF(x=10.0, y=10.0, w=20.0, h=20.0)),
            ("ent_a", RectF(x=20.0, y=20.0, w=20.0, h=20.0)),
            ("ent_m", RectF(x=30.0, y=30.0, w=20.0, h=20.0)),
        ]
        result = compute_marquee_candidates(marquee, entity_bounds)
        # Should be sorted alphabetically
        assert result == ["ent_a", "ent_m", "ent_z"]

    def test_empty_bounds_list(self) -> None:
        marquee = RectF(x=0.0, y=0.0, w=100.0, h=100.0)
        result = compute_marquee_candidates(marquee, [])
        assert result == []


# -----------------------------------------------------------------------------
# apply_marquee_selection
# -----------------------------------------------------------------------------


class TestApplyMarqueeSelection:
    """Tests for apply_marquee_selection function."""

    def test_replace_mode_returns_marquee_ids(self) -> None:
        current = ["ent_x", "ent_y"]
        marquee = ["ent_a", "ent_b"]
        result = apply_marquee_selection(current, marquee, shift=False)
        assert result == ["ent_a", "ent_b"]

    def test_replace_mode_empty_marquee(self) -> None:
        current = ["ent_x", "ent_y"]
        marquee: list[str] = []
        result = apply_marquee_selection(current, marquee, shift=False)
        assert result == []

    def test_shift_toggle_adds_new(self) -> None:
        current = ["ent_a"]
        marquee = ["ent_b", "ent_c"]
        result = apply_marquee_selection(current, marquee, shift=True)
        # ent_a kept, ent_b and ent_c added
        assert "ent_a" in result
        assert "ent_b" in result
        assert "ent_c" in result

    def test_shift_toggle_removes_existing(self) -> None:
        current = ["ent_a", "ent_b"]
        marquee = ["ent_b"]  # Only ent_b in marquee
        result = apply_marquee_selection(current, marquee, shift=True)
        # ent_b should be removed
        assert result == ["ent_a"]

    def test_shift_toggle_mixed(self) -> None:
        current = ["ent_a", "ent_b"]
        marquee = ["ent_b", "ent_c"]  # ent_b to remove, ent_c to add
        result = apply_marquee_selection(current, marquee, shift=True)
        # ent_a stays, ent_b removed, ent_c added
        assert "ent_a" in result
        assert "ent_b" not in result
        assert "ent_c" in result

    def test_shift_maintains_order_for_retained(self) -> None:
        current = ["ent_z", "ent_a", "ent_m"]
        marquee = ["ent_x"]  # Add new item
        result = apply_marquee_selection(current, marquee, shift=True)
        # Original order preserved for retained items
        assert result.index("ent_z") < result.index("ent_a")
        assert result.index("ent_a") < result.index("ent_m")
        # New item appended
        assert "ent_x" in result

    def test_shift_empty_marquee_keeps_current(self) -> None:
        current = ["ent_a", "ent_b"]
        marquee: list[str] = []
        result = apply_marquee_selection(current, marquee, shift=True)
        assert result == ["ent_a", "ent_b"]


# -----------------------------------------------------------------------------
# should_start_marquee
# -----------------------------------------------------------------------------


class TestShouldStartMarquee:
    """Tests for should_start_marquee function."""

    def test_start_on_empty_space(self) -> None:
        assert should_start_marquee(
            clicked_entity_id=None,
            clicked_gizmo=False,
            editor_mode_active=True,
        ) is True

    def test_no_start_when_editor_inactive(self) -> None:
        assert should_start_marquee(
            clicked_entity_id=None,
            clicked_gizmo=False,
            editor_mode_active=False,
        ) is False

    def test_no_start_when_entity_clicked(self) -> None:
        assert should_start_marquee(
            clicked_entity_id="some_entity",
            clicked_gizmo=False,
            editor_mode_active=True,
        ) is False

    def test_no_start_when_gizmo_clicked(self) -> None:
        assert should_start_marquee(
            clicked_entity_id=None,
            clicked_gizmo=True,
            editor_mode_active=True,
        ) is False


# -----------------------------------------------------------------------------
# get_marquee_rect_from_state
# -----------------------------------------------------------------------------


class TestGetMarqueeRectFromState:
    """Tests for get_marquee_rect_from_state function."""

    def test_returns_none_when_inactive(self) -> None:
        state = MarqueeState(
            active=False,
            start_world=(0.0, 0.0),
            end_world=(100.0, 100.0),
            shift=False,
        )
        assert get_marquee_rect_from_state(state) is None

    def test_returns_rect_when_active(self) -> None:
        state = MarqueeState(
            active=True,
            start_world=(0.0, 0.0),
            end_world=(100.0, 100.0),
            shift=False,
        )
        rect = get_marquee_rect_from_state(state)
        assert rect is not None
        assert rect.w == 100.0
        assert rect.h == 100.0


# -----------------------------------------------------------------------------
# MarqueeState dataclass
# -----------------------------------------------------------------------------


class TestMarqueeState:
    """Tests for MarqueeState dataclass."""

    def test_creation(self) -> None:
        state = MarqueeState(
            active=True,
            start_world=(10.0, 20.0),
            end_world=(100.0, 200.0),
            shift=True,
        )
        assert state.active is True
        assert state.start_world == (10.0, 20.0)
        assert state.end_world == (100.0, 200.0)
        assert state.shift is True

    def test_frozen(self) -> None:
        state = MarqueeState(
            active=True,
            start_world=(0.0, 0.0),
            end_world=(100.0, 100.0),
            shift=False,
        )
        with pytest.raises(AttributeError):
            as_any(state).active = False
