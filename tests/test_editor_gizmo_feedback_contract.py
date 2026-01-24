"""Contract tests for editor_gizmo_feedback module.

Tests gizmo feedback formatting functions as pure functions - headless, no arcade dependency.
"""

from __future__ import annotations

import pytest

from engine.editor.editor_gizmo_feedback import (
    GizmoFeedbackState,
    GizmoFeedbackLines,
    format_move_delta,
    format_rotate_delta,
    format_scale_factor,
    build_gizmo_feedback_lines,
    compute_pivot_marker_segments,
    compute_feedback_box_layout,
)


# -----------------------------------------------------------------------------
# format_move_delta
# -----------------------------------------------------------------------------


class TestFormatMoveDelta:
    """Tests for format_move_delta function."""

    def test_positive_delta(self) -> None:
        result = format_move_delta(16.0, 8.0)
        assert "Δx" in result
        assert "+16.0" in result
        assert "Δy" in result
        assert "+8.0" in result

    def test_negative_delta(self) -> None:
        result = format_move_delta(-5.5, -3.2)
        assert "-5.5" in result
        assert "-3.2" in result

    def test_zero_delta(self) -> None:
        result = format_move_delta(0.0, 0.0)
        assert "+0.0" in result

    def test_mixed_signs(self) -> None:
        result = format_move_delta(10.0, -20.0)
        assert "+10.0" in result
        assert "-20.0" in result


# -----------------------------------------------------------------------------
# format_rotate_delta
# -----------------------------------------------------------------------------


class TestFormatRotateDelta:
    """Tests for format_rotate_delta function."""

    def test_positive_rotation(self) -> None:
        result = format_rotate_delta(45.0)
        assert "Δθ" in result
        assert "+45.0" in result or "+45°" in result

    def test_negative_rotation(self) -> None:
        result = format_rotate_delta(-30.0)
        assert "-30.0" in result or "-30°" in result

    def test_zero_rotation(self) -> None:
        result = format_rotate_delta(0.0)
        assert "+0.0" in result or "0.0" in result

    def test_includes_degree_symbol(self) -> None:
        result = format_rotate_delta(90.0)
        assert "°" in result


# -----------------------------------------------------------------------------
# format_scale_factor
# -----------------------------------------------------------------------------


class TestFormatScaleFactor:
    """Tests for format_scale_factor function."""

    def test_scale_up(self) -> None:
        result = format_scale_factor(1.5)
        assert "1.5" in result or "x1.5" in result

    def test_scale_down(self) -> None:
        result = format_scale_factor(0.5)
        assert "0.5" in result or "x0.5" in result

    def test_unity_scale(self) -> None:
        result = format_scale_factor(1.0)
        assert "1.0" in result

    def test_includes_scale_label(self) -> None:
        result = format_scale_factor(2.0)
        # Should have some kind of scale indicator
        assert "Scale" in result or "x" in result


# -----------------------------------------------------------------------------
# build_gizmo_feedback_lines
# -----------------------------------------------------------------------------


class TestBuildGizmoFeedbackLines:
    """Tests for build_gizmo_feedback_lines function."""

    def test_inactive_returns_empty(self) -> None:
        state = GizmoFeedbackState(
            active=False,
            mode="move",
            pivot_xy=(0.0, 0.0),
            move_delta_xy=None,
            rotate_delta_deg=None,
            scale_factor=None,
            snap_active=False,
        )
        result = build_gizmo_feedback_lines(state)
        assert result is None

    def test_move_mode_produces_lines(self) -> None:
        state = GizmoFeedbackState(
            active=True,
            mode="move",
            pivot_xy=(100.0, 100.0),
            move_delta_xy=(16.0, -8.0),
            rotate_delta_deg=None,
            scale_factor=None,
            snap_active=False,
        )
        result = build_gizmo_feedback_lines(state)
        assert result is not None
        assert isinstance(result, GizmoFeedbackLines)
        assert result.title != ""
        assert result.line1 != ""

    def test_rotate_mode_produces_lines(self) -> None:
        state = GizmoFeedbackState(
            active=True,
            mode="rotate",
            pivot_xy=(100.0, 100.0),
            move_delta_xy=None,
            rotate_delta_deg=45.0,
            scale_factor=None,
            snap_active=False,
        )
        result = build_gizmo_feedback_lines(state)
        assert result is not None
        assert "Rotate" in result.title or "ROTATE" in result.title

    def test_scale_mode_produces_lines(self) -> None:
        state = GizmoFeedbackState(
            active=True,
            mode="scale",
            pivot_xy=(100.0, 100.0),
            move_delta_xy=None,
            rotate_delta_deg=None,
            scale_factor=1.5,
            snap_active=False,
        )
        result = build_gizmo_feedback_lines(state)
        assert result is not None
        assert "Scale" in result.title or "SCALE" in result.title

    def test_snap_active_shows_indicator(self) -> None:
        state = GizmoFeedbackState(
            active=True,
            mode="move",
            pivot_xy=(100.0, 100.0),
            move_delta_xy=(16.0, 0.0),
            rotate_delta_deg=None,
            scale_factor=None,
            snap_active=True,
        )
        result = build_gizmo_feedback_lines(state)
        assert result is not None
        # Should indicate snapping somewhere
        assert result.line2 is not None
        assert "Snap" in result.line2 or "SNAP" in result.line2 or "snap" in result.line2


# -----------------------------------------------------------------------------
# compute_pivot_marker_segments
# -----------------------------------------------------------------------------


class TestComputePivotMarkerSegments:
    """Tests for compute_pivot_marker_segments function."""

    def test_returns_two_segments(self) -> None:
        h_seg, v_seg = compute_pivot_marker_segments((100.0, 100.0), 10.0)
        assert h_seg is not None
        assert v_seg is not None

    def test_horizontal_segment_shape(self) -> None:
        h_seg, _ = compute_pivot_marker_segments((100.0, 100.0), 10.0)
        x1, y1, x2, y2 = h_seg
        # Horizontal segment should have same y
        assert y1 == y2
        # And should span around pivot
        assert x1 < 100.0 < x2

    def test_vertical_segment_shape(self) -> None:
        _, v_seg = compute_pivot_marker_segments((100.0, 100.0), 10.0)
        x1, y1, x2, y2 = v_seg
        # Vertical segment should have same x
        assert x1 == x2
        # And should span around pivot
        assert y1 < 100.0 < y2

    def test_segments_use_half_size(self) -> None:
        half_size = 8.0
        h_seg, v_seg = compute_pivot_marker_segments((0.0, 0.0), half_size)
        x1, _, x2, _ = h_seg
        assert x2 - x1 == pytest.approx(half_size * 2)


# -----------------------------------------------------------------------------
# compute_feedback_box_layout
# -----------------------------------------------------------------------------


class TestComputeFeedbackBoxLayout:
    """Tests for compute_feedback_box_layout function."""

    def test_returns_position_and_size(self) -> None:
        lines = GizmoFeedbackLines(title="Move", line1="Δx +16.0  Δy -8.0", line2=None)
        result = compute_feedback_box_layout(1280, 720, lines)
        assert "box_x" in result
        assert "box_y" in result
        assert "box_width" in result
        assert "box_height" in result

    def test_positioned_in_viewport(self) -> None:
        lines = GizmoFeedbackLines(title="Move", line1="Δx +16.0  Δy -8.0", line2=None)
        result = compute_feedback_box_layout(1280, 720, lines)
        # Should be positioned somewhere reasonable
        assert 0 <= result["box_x"] <= 1280
        assert 0 <= result["box_y"] <= 720

    def test_reasonable_size(self) -> None:
        lines = GizmoFeedbackLines(title="Move", line1="Δx +16.0  Δy -8.0", line2=None)
        result = compute_feedback_box_layout(1280, 720, lines)
        # Should have reasonable size for text
        assert result["box_width"] > 50
        assert result["box_height"] > 20


# -----------------------------------------------------------------------------
# GizmoFeedbackState dataclass
# -----------------------------------------------------------------------------


class TestGizmoFeedbackState:
    """Tests for GizmoFeedbackState dataclass."""

    def test_create_inactive(self) -> None:
        state = GizmoFeedbackState(
            active=False,
            mode="move",
            pivot_xy=(0.0, 0.0),
            move_delta_xy=None,
            rotate_delta_deg=None,
            scale_factor=None,
            snap_active=False,
        )
        assert state.active is False

    def test_create_move_active(self) -> None:
        state = GizmoFeedbackState(
            active=True,
            mode="move",
            pivot_xy=(100.0, 200.0),
            move_delta_xy=(10.0, 20.0),
            rotate_delta_deg=None,
            scale_factor=None,
            snap_active=True,
        )
        assert state.active is True
        assert state.mode == "move"
        assert state.pivot_xy == (100.0, 200.0)
        assert state.move_delta_xy == (10.0, 20.0)
        assert state.snap_active is True


# -----------------------------------------------------------------------------
# GizmoFeedbackLines dataclass
# -----------------------------------------------------------------------------


class TestGizmoFeedbackLines:
    """Tests for GizmoFeedbackLines dataclass."""

    def test_create_with_all_lines(self) -> None:
        lines = GizmoFeedbackLines(
            title="Move",
            line1="Δx +10  Δy +20",
            line2="[Snap]",
        )
        assert lines.title == "Move"
        assert lines.line1 == "Δx +10  Δy +20"
        assert lines.line2 == "[Snap]"

    def test_create_without_line2(self) -> None:
        lines = GizmoFeedbackLines(
            title="Rotate",
            line1="Δθ +45°",
            line2=None,
        )
        assert lines.line2 is None
