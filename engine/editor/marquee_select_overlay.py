"""Editor overlay for marquee box selection rectangle.

Renders the marquee selection rectangle in world space during drag.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import engine.optional_arcade as optional_arcade

from ..logging_tools import get_logger
from ..ui_overlays.common import UIElement
from .selection_outline import RectF, rect_to_border_segments

if TYPE_CHECKING:
    from engine.editor_controller import EditorModeController

logger = get_logger(__name__)

# Colors (RGBA)
MARQUEE_BORDER_COLOR = (100, 200, 255, 255)  # Cyan border
MARQUEE_FILL_COLOR = (100, 200, 255, 30)  # Cyan fill with low alpha

# Line width
MARQUEE_LINE_WIDTH = 1.5


class MarqueeSelectOverlay(UIElement):
    """Overlay for rendering marquee selection rectangle in world space."""

    def __init__(self, window: Any) -> None:
        """Initialize overlay.

        Args:
            window: Game window to query controller from.
        """
        super().__init__(window)
        self._visible = True

    @property
    def controller(self) -> "EditorModeController | None":
        """Get editor controller from window."""
        return getattr(self.window, "editor_controller", None)

    def update(self, dt: float) -> None:  # noqa: ARG002
        """Update overlay (no-op for this overlay)."""
        pass

    def draw(self) -> None:
        """Draw overlay (delegates to draw_world for marquee rect)."""
        # Marquee is drawn in world space by draw_world, called separately
        pass

    def draw_world(self) -> None:
        """Draw world-space marquee selection rectangle.

        Should be called within the world camera context.
        """
        controller = self.controller
        if controller is None or not getattr(controller, "active", False):
            return

        if not self._visible:
            return

        # Get marquee rect from controller
        rect = self._get_marquee_rect(controller)
        if rect is None:
            return

        arcade = optional_arcade.arcade
        self._draw_marquee_rect(arcade, rect)

    def draw_ui(self) -> None:
        """Draw UI elements (none for marquee)."""
        pass

    def _get_marquee_rect(self, controller: Any) -> RectF | None:
        """Get current marquee rectangle from controller.

        Args:
            controller: Editor controller.

        Returns:
            RectF if marquee is active, None otherwise.
        """
        # Check if marquee is active
        if not getattr(controller, "_marquee_active", False):
            return None

        start = getattr(controller, "_marquee_start_world", None)
        end = getattr(controller, "_marquee_end_world", None)

        if start is None or end is None:
            return None

        # Build rect from points
        from .marquee_select import rect_from_points  # noqa: PLC0415
        return rect_from_points(start, end)

    def _draw_marquee_rect(self, arcade: Any, rect: RectF) -> None:
        """Draw the marquee rectangle.

        Args:
            arcade: Arcade module reference.
            rect: Rectangle to draw.
        """
        # Draw filled rectangle with low alpha
        draw_rect_filled = getattr(arcade, "draw_lbwh_rectangle_filled", None)
        if draw_rect_filled is not None:
            try:
                draw_rect_filled(
                    rect.left, rect.bottom, rect.w, rect.h,
                    MARQUEE_FILL_COLOR
                )
            except (AttributeError, TypeError):
                pass

        # Draw border
        segments = rect_to_border_segments(rect)
        draw_line = getattr(arcade, "draw_line", None)

        if draw_line is not None:
            try:
                for seg in segments:
                    draw_line(seg[0], seg[1], seg[2], seg[3], MARQUEE_BORDER_COLOR, MARQUEE_LINE_WIDTH)
            except (AttributeError, TypeError):
                pass
