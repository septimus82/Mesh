"""Editor tooltip overlay.

Displays a small tooltip box near the mouse cursor when hovering
interactive editor UI elements.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import engine.optional_arcade as optional_arcade

from .text_draw import TextCache, draw_text_cached
from .ui_overlays.common import UIElement

if TYPE_CHECKING:
    from .game import GameWindow


# Styling constants
TOOLTIP_BG_COLOR = (25, 25, 30, 240)
TOOLTIP_BORDER_COLOR = (60, 60, 70, 255)
TOOLTIP_TEXT_COLOR = (220, 220, 220, 255)
TOOLTIP_FONT_SIZE = 11


class EditorTooltipOverlay(UIElement):
    """Overlay that draws tooltip near the mouse position."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self._text_cache = TextCache(max_size=32)

    def draw(self) -> None:
        """Draw tooltip if editor is active and a tooltip target is hovered."""
        controller = getattr(self.window, "editor_controller", None)
        if controller is None or not getattr(controller, "active", False):
            return

        # Get mouse position
        get_mouse_pos = getattr(controller, "get_last_mouse_pos", None)
        if not callable(get_mouse_pos):
            return

        try:
            mouse_x, mouse_y = get_mouse_pos()
        except Exception:  # noqa: BLE001  # REASON: cursor position hooks are optional and should not block tooltip overlay updates
            return

        # Get window dimensions
        window_w = int(getattr(self.window, "width", 800) or 800)
        window_h = int(getattr(self.window, "height", 600) or 600)

        # Resolve tooltip text
        from .editor_tooltips_model import (
            compute_tooltip_box_layout,
            resolve_editor_tooltip,
        )

        tooltip_text = resolve_editor_tooltip(
            controller, mouse_x, mouse_y, window_w, window_h
        )
        if not tooltip_text:
            return

        # Compute tooltip layout
        layout = compute_tooltip_box_layout(
            mouse_x, mouse_y, tooltip_text, window_w, window_h
        )

        # Draw background
        optional_arcade.arcade.draw_lrbt_rectangle_filled(
            layout.x,
            layout.x + layout.w,
            layout.y,
            layout.y + layout.h,
            TOOLTIP_BG_COLOR,
        )

        # Draw border
        optional_arcade.arcade.draw_lrbt_rectangle_outline(
            layout.x,
            layout.x + layout.w,
            layout.y,
            layout.y + layout.h,
            TOOLTIP_BORDER_COLOR,
            1,
        )

        # Draw text
        cache = getattr(self.window, "text_cache", None) or self._text_cache
        text_x = layout.x + 8
        text_y = layout.y + layout.h / 2

        draw_text_cached(
            tooltip_text,
            text_x,
            text_y,
            color=TOOLTIP_TEXT_COLOR,
            font_size=TOOLTIP_FONT_SIZE,
            anchor_y="center",
            cache=cache,
        )
