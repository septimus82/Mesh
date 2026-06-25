"""Context menu overlay for the editor.

This overlay renders the right-click context menu in the editor.
Draws only when editor mode is active and context menu is open.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import engine.optional_arcade as optional_arcade

from ..text_draw import TextCache, draw_text_cached
from .common import UIElement, draw_panel_bg
from .theme import EDITOR_THEME

if TYPE_CHECKING:  # pragma: no cover
    from ..game import GameWindow


CONTEXT_BG_COLOR = EDITOR_THEME.panel_bg
CONTEXT_BORDER_COLOR = EDITOR_THEME.chrome_border
CONTEXT_HOVER_COLOR = EDITOR_THEME.chrome_accent
CONTEXT_TEXT_COLOR = EDITOR_THEME.chrome_text
CONTEXT_TEXT_DISABLED_COLOR = EDITOR_THEME.chrome_separator
CONTEXT_SHORTCUT_COLOR = EDITOR_THEME.chrome_dim


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
        from engine.editor.editor_panels_query import panels_is_open  # noqa: PLC0415

        if not panels_is_open(controller, "context_menu"):
            return

        # Import here to avoid circular imports
        from engine.editor.editor_menu_hover_query import get_context_menu_hover_id

        from ..editor.context_menu_model import (
            CONTEXT_MENU_FONT_SIZE,
            build_context_menu_items,
            compute_context_menu_layout,
        )

        # Get current state
        menu_x = getattr(controller, "_context_menu_x", 0)
        menu_y = getattr(controller, "_context_menu_y", 0)
        hover_id = get_context_menu_hover_id(controller)

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
            if item.separator:
                line_y = item_rect.y + item_rect.h / 2
                optional_arcade.arcade.draw_line(
                    item_rect.x + 8,
                    line_y,
                    item_rect.x + item_rect.w - 8,
                    line_y,
                    CONTEXT_BORDER_COLOR,
                    1,
                )
                continue

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
