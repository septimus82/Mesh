"""Menu bar overlay for the editor.

This overlay renders the menu bar and dropdown menus in the editor.
Draws only when editor mode is active.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import engine.optional_arcade as optional_arcade
from engine.editor.editor_menu_hover_query import get_menu_hover_item_id
from engine.editor.editor_modal_state_query import get_active_menu_id

from ..text_draw import draw_text_cached, TextCache
from .common import UIElement, draw_panel_bg

if TYPE_CHECKING:  # pragma: no cover
    from ..game import GameWindow


# Color palette for the menu bar
MENU_BG_COLOR = (40, 40, 45, 255)
MENU_HOVER_COLOR = (60, 60, 70, 255)
MENU_ACTIVE_COLOR = (70, 130, 180, 255)
MENU_TEXT_COLOR = (220, 220, 220, 255)
MENU_TEXT_DISABLED_COLOR = (100, 100, 100, 255)
MENU_DROPDOWN_BG_COLOR = (35, 35, 40, 250)
MENU_DROPDOWN_BORDER_COLOR = (60, 60, 70, 255)
MENU_SEPARATOR_COLOR = (60, 60, 70, 255)
MENU_SHORTCUT_COLOR = (140, 140, 140, 255)


class MenuBarOverlay(UIElement):
    """Editor-only overlay that draws the menu bar."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self._text_cache = TextCache(max_size=64)

    def draw(self) -> None:
        """Draw the menu bar overlay."""
        controller = getattr(self.window, "editor_mode_controller", None)
        if controller is None:
            return
        if not getattr(controller, "active", False):
            return

        # Import here to avoid circular imports
        from ..editor.menu_bar_model import (
            build_menu_groups,
            compute_menu_bar_layout,
            get_dropdown_bounds,
            MENU_BAR_HEIGHT,
            MENU_FONT_SIZE,
        )

        # Get current state
        active_menu = get_active_menu_id(controller)
        hover_item_id = get_menu_hover_item_id(controller)

        # Build layout
        menu_groups = build_menu_groups(controller, self.window)
        layout = compute_menu_bar_layout(
            self.window.width,
            self.window.height,
            menu_groups,
            active_menu,
        )

        # Draw menu bar background
        bar = layout.bar_rect
        draw_panel_bg(bar.x, bar.x + bar.w, bar.y, bar.y + bar.h, MENU_BG_COLOR)

        # Draw menu titles
        for group in menu_groups:
            title_rect = layout.titles.get(group.title)
            if title_rect is None:
                continue

            # Highlight active or hovered title
            if active_menu == group.title:
                draw_panel_bg(
                    title_rect.x,
                    title_rect.x + title_rect.w,
                    title_rect.y,
                    title_rect.y + title_rect.h,
                    MENU_ACTIVE_COLOR,
                )
            elif self._is_title_hovered(controller, title_rect):
                draw_panel_bg(
                    title_rect.x,
                    title_rect.x + title_rect.w,
                    title_rect.y,
                    title_rect.y + title_rect.h,
                    MENU_HOVER_COLOR,
                )

            # Draw title text
            text_x = title_rect.x + title_rect.w / 2
            text_y = title_rect.y + title_rect.h / 2 - 2
            draw_text_cached(
                group.title,
                text_x,
                text_y,
                color=MENU_TEXT_COLOR,
                font_size=MENU_FONT_SIZE,
                anchor_x="center",
                cache=self._text_cache,
            )

        # Draw dropdown if active
        if layout.dropdown:
            dropdown_bounds = get_dropdown_bounds(layout)
            if dropdown_bounds:
                # Draw dropdown background
                draw_panel_bg(
                    dropdown_bounds.x,
                    dropdown_bounds.x + dropdown_bounds.w,
                    dropdown_bounds.y,
                    dropdown_bounds.y + dropdown_bounds.h,
                    MENU_DROPDOWN_BG_COLOR,
                )
                # Draw dropdown border
                optional_arcade.arcade.draw_lrbt_rectangle_outline(
                    dropdown_bounds.x,
                    dropdown_bounds.x + dropdown_bounds.w,
                    dropdown_bounds.y,
                    dropdown_bounds.y + dropdown_bounds.h,
                    MENU_DROPDOWN_BORDER_COLOR,
                    1,
                )

            # Draw items
            for item, item_rect in layout.dropdown:
                if item.label == "-":
                    # Draw separator
                    sep_y = item_rect.y + item_rect.h / 2
                    optional_arcade.arcade.draw_line(
                        item_rect.x + 8,
                        sep_y,
                        item_rect.x + item_rect.w - 8,
                        sep_y,
                        MENU_SEPARATOR_COLOR,
                        1,
                    )
                else:
                    # Highlight hovered item
                    if item.enabled and item.id == hover_item_id:
                        draw_panel_bg(
                            item_rect.x,
                            item_rect.x + item_rect.w,
                            item_rect.y,
                            item_rect.y + item_rect.h,
                            MENU_ACTIVE_COLOR,
                        )

                    # Draw item label
                    text_color = MENU_TEXT_COLOR if item.enabled else MENU_TEXT_DISABLED_COLOR
                    text_x = item_rect.x + 12
                    text_y = item_rect.y + item_rect.h / 2 - 2
                    draw_text_cached(
                        item.label,
                        text_x,
                        text_y,
                        color=text_color,
                        font_size=MENU_FONT_SIZE,
                        cache=self._text_cache,
                    )

                    # Draw shortcut if present
                    if item.shortcut:
                        shortcut_x = item_rect.x + item_rect.w - 12
                        shortcut_color = MENU_SHORTCUT_COLOR if item.enabled else MENU_TEXT_DISABLED_COLOR
                        draw_text_cached(
                            item.shortcut,
                            shortcut_x,
                            text_y,
                            color=shortcut_color,
                            font_size=MENU_FONT_SIZE - 1,
                            anchor_x="right",
                            cache=self._text_cache,
                        )

    def _is_title_hovered(self, controller: object, title_rect: object) -> bool:
        """Check if a menu title is hovered."""
        from ..editor.menu_bar_model import MenuRect

        if not isinstance(title_rect, MenuRect):
            return False

        mouse_x = getattr(self.window, "_mouse_x", 0)
        mouse_y = getattr(self.window, "_mouse_y", 0)
        return title_rect.contains_point(mouse_x, mouse_y)
