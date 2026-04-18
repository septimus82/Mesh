"""Overlay for the Project Explorer Context Menu.

Renders the context menu managed by ProjectExplorerContextMenuController.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Tuple

import engine.optional_arcade as optional_arcade
from .common import UIElement, _draw_rectangle_filled, _draw_lrtb_rectangle_outline
from ..text_draw import TextCache
from ..ui_text_cache import UiTextCache, draw_text
from .providers import project_explorer_context_menu_provider

if TYPE_CHECKING:
    from ..game import GameWindow

class ProjectExplorerContextMenuOverlay(UIElement):
    """Draws the project explorer context menu."""
    
    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self._ui_cache = UiTextCache(TextCache(max_size=32))
        
    def draw(self) -> None:
        from ..editor.project_explorer_context_menu_layout_model import clamp_menu_rect
        from ..editor.project_explorer_context_menu_model import (
            CONTEXT_MENU_BG_COLOR,
            CONTEXT_MENU_BORDER_COLOR,
            CONTEXT_MENU_DISABLED_TEXT_COLOR,
            CONTEXT_MENU_FONT_SIZE,
            CONTEXT_MENU_HOVER_COLOR,
            CONTEXT_MENU_ITEM_HEIGHT,
            CONTEXT_MENU_PADDING_X,
            CONTEXT_MENU_PADDING_Y,
            CONTEXT_MENU_TEXT_COLOR,
            CONTEXT_MENU_WIDTH,
        )

        payload = project_explorer_context_menu_provider(self.window)
        if not payload or not payload.get("open"):
            return
        items = payload.get("items", [])
        if not isinstance(items, list) or not items:
            return

        # Geometry + clamp
        anchor_x = int(payload.get("anchor_x", 0))
        anchor_y = int(payload.get("anchor_y", 0))
        w = int(payload.get("preferred_width", CONTEXT_MENU_WIDTH))
        h = int(payload.get("height", 0))
        if h <= 0:
            return
        viewport_w = int(payload.get("viewport_w", getattr(self.window, "width", 1280) or 1280))
        viewport_h = int(payload.get("viewport_h", getattr(self.window, "height", 720) or 720))
        mx, my = clamp_menu_rect(anchor_x, anchor_y, w, h, viewport_w, viewport_h)
        
        # 1. Background
        # Note: _draw_rectangle_filled takes (x, width, y, height) in centered system?
        # Checking implementations used elsewhere: 
        # _draw_rectangle_filled(center_x, center_y, width, height, color) usually
        # But let's check common.py logic or just use arcade directly if obscure.
        # "common" says: def _draw_rectangle_filled(x, y, width, height, color): ...
        
        # Let's rely on arcade LTRB for absolute positioning clarity
        left, right = mx, mx + w
        # Y is traditionally bottom-up in Arcade, but menus often computed top-down.
        # However, our controller computes window-relative coordinates where (0,0) might be bottom-left?
        # GameWindow usually uses bottom-left origin. Mouse y is also bottom-left.
        # If we positioned menu "at mouse", and clamped, we likely treat y as bottom-left.
        # The menu height extends *Up*? 
        # Standard menus extend *Down*.
        # Let's assume standard Desktop behavior: Click at (x,y), menu top-left is (x,y), extends to (x, y-h).
        # Ah, Arcade coords: (0,0) is bottom-left.
        # Mouse (x,y) is (0 at left, 0 at bottom).
        # So "Down" means decreasing Y.
        # "menu extends down" means top is at Y, bottom is at Y - H.
        # Our clamp logic in model checked "if y + h > viewport_h". This implies Y is bottom-left of menu?
        # If Y was top-left, we'd check "if y < 0".
        # Let's Stick to standard arcade rect: (x, y, w, h) usually means (left, bottom, width, height).
        # So Controller.position (x,y) is the *bottom-left* corner?
        # No, typically you click and that's the *top-left*.
        # So Position = TopLeft.
        # Bottom = TopLeft Y - Height.
        # But wait, clamp logic:
        # `if final_y + menu_h > viewport_h: final_y = max(0, viewport_h - menu_h)`
        # If Y is bottom-left, then Y+H is top. This logic ensures top is within screen.
        # Thus, Controller.position (x,y) is the BOTTOM-LEFT corner of the menu rect.
        
        b = my
        t = my + h
        
        # Subtle shadow + panel
        optional_arcade.arcade.draw_lrtb_rectangle_filled(left + 1, right + 1, t - 1, b - 1, (0, 0, 0, 120))
        optional_arcade.arcade.draw_lrtb_rectangle_filled(left, right, t, b, CONTEXT_MENU_BG_COLOR)
        optional_arcade.arcade.draw_lrtb_rectangle_outline(left, right, t, b, CONTEXT_MENU_BORDER_COLOR, 1)
        
        # 2. Items
        # Render top to bottom
        # Item 0 is at top. 
        # Top internal Y = t - PADDING_Y
        
        start_y = t - CONTEXT_MENU_PADDING_Y
        
        hover_idx = payload.get("hover_index", None)
        selected_idx = payload.get("index", None)
        left_pad = CONTEXT_MENU_PADDING_X + 2
        right_pad = CONTEXT_MENU_PADDING_X + 2
        label_gutter = 6
        approx_char_w = max(1.0, CONTEXT_MENU_FONT_SIZE * 0.6)
        for i, item in enumerate(items):
            item_top = start_y - (i * CONTEXT_MENU_ITEM_HEIGHT)
            item_bottom = item_top - CONTEXT_MENU_ITEM_HEIGHT
            
            # Hover
            if item.kind != "separator" and (i == hover_idx or (hover_idx is None and i == selected_idx)):
                optional_arcade.arcade.draw_lrtb_rectangle_filled(
                    left + 1, right - 1, item_top, item_bottom, CONTEXT_MENU_HOVER_COLOR
                )
                
            # Text
            if item.kind == "separator":
                mid_y = (item_top + item_bottom) / 2
                optional_arcade.arcade.draw_line(
                    left + left_pad, mid_y, right - right_pad, mid_y, CONTEXT_MENU_BORDER_COLOR, 1
                )
                continue

            if item.enabled:
                text_color = CONTEXT_MENU_TEXT_COLOR
                shortcut_alpha = 200
            else:
                text_color = (CONTEXT_MENU_DISABLED_TEXT_COLOR[0], CONTEXT_MENU_DISABLED_TEXT_COLOR[1], CONTEXT_MENU_DISABLED_TEXT_COLOR[2], 130)
                shortcut_alpha = 130
            
            # Label
            # anchors: left, center_y
            cx = left + left_pad
            cy = item_bottom + (CONTEXT_MENU_ITEM_HEIGHT / 2)
            
            shortcut = getattr(item, "shortcut_text", None) or ""
            sc_x = right - right_pad
            max_label_w = max(0.0, (sc_x - label_gutter) - cx)
            max_label_chars = int(max_label_w / approx_char_w) if max_label_w > 0 else 0
            label_text = str(item.title or "")
            if max_label_chars > 0 and len(label_text) > max_label_chars:
                if max_label_chars >= 3:
                    label_text = label_text[: max(0, max_label_chars - 3)] + "..."
                else:
                    label_text = label_text[:max_label_chars]

            draw_text(
                self._ui_cache,
                text=label_text,
                x=cx,
                y=cy,
                color=text_color,
                font_size=CONTEXT_MENU_FONT_SIZE,
                anchor_x="left",
                anchor_y="center",
            )
            
            # Shortcut (Right aligned)
            if shortcut:
                sc_color = (text_color[0], text_color[1], text_color[2], shortcut_alpha)
                draw_text(
                    self._ui_cache,
                    text=str(shortcut),
                    x=sc_x,
                    y=cy,
                    color=sc_color,
                    font_size=CONTEXT_MENU_FONT_SIZE,
                    anchor_x="right",
                    anchor_y="center",
                )

        # --- Scrollbar (render-only, if payload provides scroll context) ---
        total_count = payload.get("total_count")
        visible_count = payload.get("visible_count")
        start_index = payload.get("start_index")
        rows_visible = payload.get("rows_visible")
        if total_count is None and rows_visible is not None:
            try:
                visible_count = len(rows_visible)
            except Exception:
                visible_count = None
        if total_count is not None and visible_count is not None and start_index is not None:
            try:
                total_n = int(total_count)
                visible_n = int(visible_count)
                start_n = int(start_index)
            except Exception:
                total_n = 0
                visible_n = 0
                start_n = 0
            if total_n > 0 and visible_n > 0 and total_n > visible_n:
                track_left = right - 3
                track_right = right - 1
                track_top = t - CONTEXT_MENU_PADDING_Y
                track_bottom = b + CONTEXT_MENU_PADDING_Y
                optional_arcade.arcade.draw_lrtb_rectangle_filled(
                    track_left, track_right, track_top, track_bottom, (90, 90, 100, 140)
                )
                track_h = max(1.0, track_top - track_bottom)
                ratio = max(0.0, min(1.0, start_n / max(1, (total_n - visible_n))))
                thumb_h = max(8.0, track_h * (visible_n / total_n))
                usable_h = max(1.0, track_h - thumb_h)
                thumb_top = track_top - (ratio * usable_h)
                thumb_bottom = thumb_top - thumb_h
                optional_arcade.arcade.draw_lrtb_rectangle_filled(
                    track_left, track_right, thumb_top, thumb_bottom, (150, 150, 160, 200)
                )
