"""Editor gizmo overlay for transform feedback display.

Renders pivot markers and delta readouts during transform operations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

import engine.optional_arcade as optional_arcade
from ..logging_tools import get_logger
from .editor_gizmo_feedback import (
    GizmoFeedbackState,
    build_gizmo_feedback_lines,
    compute_feedback_box_layout,
    compute_pivot_marker_segments,
)

if TYPE_CHECKING:
    from engine.editor_controller import EditorModeController

logger = get_logger(__name__)

# Colors
PIVOT_MARKER_COLOR = (255, 200, 50, 220)  # Yellow-orange
FEEDBACK_BOX_BG = (30, 30, 30, 200)  # Dark translucent
FEEDBACK_TEXT_COLOR = (240, 240, 240, 255)  # White
FEEDBACK_TITLE_COLOR = (180, 220, 255, 255)  # Light blue

# Pivot marker size in world units (will be zoom-adjusted)
PIVOT_MARKER_BASE_SIZE = 12.0
PIVOT_MARKER_LINE_WIDTH = 2.0


class EditorGizmoOverlay:
    """Overlay for gizmo feedback during transform operations."""

    def __init__(self, window: Any) -> None:
        """Initialize overlay.

        Args:
            window: Game window to query controller from.
        """
        self.window = window
        self._draw_text_cached: Callable[..., Any] | None = None

    @property
    def controller(self) -> Any:
        """Get editor controller from window."""
        return getattr(self.window, "editor_controller", None)

    def update(self, dt: float) -> None:  # noqa: ARG002
        """Update overlay (no-op for this overlay)."""
        pass

    def draw(self) -> None:
        """Draw overlay (delegates to draw_world for gizmos)."""
        # Gizmos are drawn in world space by draw_world, called separately
        pass

    def _get_draw_text_cached(self) -> Any:
        """Lazy load draw_text_cached to avoid import issues."""
        if self._draw_text_cached is None:
            try:
                from engine.text_draw import draw_text_cached  # noqa: PLC0415
                self._draw_text_cached = draw_text_cached
            except ImportError:
                # Fallback to arcade draw_text if text_draw not available
                fallback: Any = getattr(
                    optional_arcade.arcade, "draw_text", lambda *a, **k: None
                )
                self._draw_text_cached = fallback
        return self._draw_text_cached

    def draw_world(self) -> None:
        """Draw world-space elements (pivot marker).

        Should be called within the world camera context.
        """
        if not getattr(self.controller, "active", False):
            return

        state = self._get_feedback_state()
        if not state.active or state.pivot_xy is None:
            return

        # Get camera zoom for size adjustment
        zoom = self._get_camera_zoom()
        marker_size = PIVOT_MARKER_BASE_SIZE / zoom if zoom > 0 else PIVOT_MARKER_BASE_SIZE

        # Compute crosshair segments
        h_seg, v_seg = compute_pivot_marker_segments(state.pivot_xy, marker_size)

        # Draw crosshair lines
        arcade = optional_arcade.arcade
        try:
            # Horizontal line
            arcade.draw_line(
                h_seg[0], h_seg[1], h_seg[2], h_seg[3],
                PIVOT_MARKER_COLOR, PIVOT_MARKER_LINE_WIDTH
            )
            # Vertical line
            arcade.draw_line(
                v_seg[0], v_seg[1], v_seg[2], v_seg[3],
                PIVOT_MARKER_COLOR, PIVOT_MARKER_LINE_WIDTH
            )
            # Small center dot
            arcade.draw_circle_filled(
                state.pivot_xy[0], state.pivot_xy[1],
                3.0 / zoom if zoom > 0 else 3.0,
                PIVOT_MARKER_COLOR
            )
        except (AttributeError, TypeError):
            # arcade_stub or missing methods
            pass

    def draw_ui(self, screen_width: float, screen_height: float) -> None:
        """Draw screen-space UI elements (feedback text box).

        Should be called after switching to UI camera context.

        Args:
            screen_width: Current screen width.
            screen_height: Current screen height.
        """
        if not getattr(self.controller, "active", False):
            return

        state = self._get_feedback_state()
        if not state.active:
            return

        lines = build_gizmo_feedback_lines(state)
        if lines is None:
            return

        layout = compute_feedback_box_layout(screen_width, screen_height, lines)

        arcade = optional_arcade.arcade
        draw_text = self._get_draw_text_cached()

        # Draw background box
        try:
            box_cx = layout["box_x"] + layout["box_width"] / 2
            box_cy = layout["box_y"] + layout["box_height"] / 2
            arcade.draw_rectangle_filled(
                box_cx, box_cy,
                layout["box_width"], layout["box_height"],
                FEEDBACK_BOX_BG
            )
        except (AttributeError, TypeError):
            pass

        # Draw text lines
        for i, pos in enumerate(layout["text_positions"]):
            color = FEEDBACK_TITLE_COLOR if i == 0 else FEEDBACK_TEXT_COLOR
            try:
                draw_text(
                    pos["text"],
                    pos["x"],
                    pos["y"],
                    color,
                    font_size=12,
                    anchor_x="left",
                    anchor_y="center",
                )
            except (AttributeError, TypeError):
                pass

    def _get_feedback_state(self) -> GizmoFeedbackState:
        """Get current feedback state from controller.

        Returns:
            GizmoFeedbackState from controller or inactive default.
        """
        getter = getattr(self.controller, "get_gizmo_feedback_state", None)
        if callable(getter):
            result = getter()
            if isinstance(result, GizmoFeedbackState):
                return result

        # Fallback: inactive state
        return GizmoFeedbackState(
            active=False,
            mode="move",
            pivot_xy=None,
            move_delta_xy=None,
            rotate_delta_deg=None,
            scale_factor=None,
            snap_active=False,
        )

    def _get_camera_zoom(self) -> float:
        """Get current camera zoom level.

        Returns:
            Camera zoom (1.0 = default), or 1.0 if unavailable.
        """
        try:
            window = getattr(self.controller, "window", None)
            if window is None:
                return 1.0
            camera_ctrl = getattr(window, "camera_controller", None)
            if camera_ctrl is None:
                return 1.0
            return float(getattr(camera_ctrl, "zoom", 1.0))
        except (AttributeError, TypeError):
            return 1.0
