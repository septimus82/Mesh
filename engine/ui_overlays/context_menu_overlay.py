"""Context menu overlay for the editor.

This overlay renders the right-click context menu in the editor.
Draws only when editor mode is active and context menu is open.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import engine.optional_arcade as optional_arcade

from ..text_draw import draw_text_cached, TextCache
from .common import UIElement, draw_panel_bg

if TYPE_CHECKING:  # pragma: no cover
    from ..game import GameWindow


# Color palette for the context menu
CONTEXT_BG_COLOR = (35, 35, 40, 250)
CONTEXT_BORDER_COLOR = (60, 60, 70, 255)
CONTEXT_HOVER_COLOR = (70, 130, 180, 255)
CONTEXT_TEXT_COLOR = (220, 220, 220, 255)
CONTEXT_TEXT_DISABLED_COLOR = (100, 100, 100, 255)
CONTEXT_SHORTCUT_COLOR = (140, 140, 140, 255)


class ContextMenuOverlay(UIElement):
    """Editor-only overlay that draws the context menu."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self._text_cache = TextCache(max_size=32)

    def draw(self) -> None:
        """Draw the context menu overlay."""
        controller = getattr(self.window, "editor_mode_controller", None)
        if controller is None:
            return
        if not getattr(controller, "active", False):
            return
        if not getattr(controller, "_context_menu_open", False):
            return

        # Import here to avoid circular imports
        from ..editor.context_menu_model import (
            build_context_menu_items,
            compute_context_menu_layout,
            CONTEXT_MENU_FONT_SIZE,
        )

        # Get current state
        menu_x = getattr(controller, "_context_menu_x", 0)
        menu_y = getattr(controller, "_context_menu_y", 0)
        hover_id = getattr(controller, "_context_menu_hover_id", None)

        # Build layout
        items = build_context_menu_items(controller)
        layout = compute_context_menu_layout(
            menu_x,
            menu_y,
            items,
            self.window.width,
            self.window.height,
        )

        # Draw menu background
        rect = layout.rect
        draw_panel_bg(rect.x, rect.x + rect.w, rect.y, rect.y + rect.h, CONTEXT_BG_COLOR)

        # Draw border
        optional_arcade.arcade.draw_lrbt_rectangle_outline(
            rect.x,
            rect.x + rect.w,
            rect.y,
            rect.y + rect.h,
            CONTEXT_BORDER_COLOR,
            1,
        )

        # Draw items
        for item, item_rect in layout.items_with_rects:
            # Highlight hovered item
            if item.enabled and item.id == hover_id:
                draw_panel_bg(
                    item_rect.x,
                    item_rect.x + item_rect.w,
                    item_rect.y,
                    item_rect.y + item_rect.h,
                    CONTEXT_HOVER_COLOR,
                )

            # Draw item label
            text_color = CONTEXT_TEXT_COLOR if item.enabled else CONTEXT_TEXT_DISABLED_COLOR
            text_x = item_rect.x + 12
            text_y = item_rect.y + item_rect.h / 2 - 2
            draw_text_cached(
                item.label,
                text_x,
                text_y,
                color=text_color,
                font_size=CONTEXT_MENU_FONT_SIZE,
                cache=self._text_cache,
            )

            # Draw shortcut if present
            if item.shortcut:
                shortcut_x = item_rect.x + item_rect.w - 12
                shortcut_color = CONTEXT_SHORTCUT_COLOR if item.enabled else CONTEXT_TEXT_DISABLED_COLOR
                draw_text_cached(
                    item.shortcut,
                    shortcut_x,
                    text_y,
                    color=shortcut_color,
                    font_size=CONTEXT_MENU_FONT_SIZE - 1,
                    anchor_x="right",
                    cache=self._text_cache,
                )
