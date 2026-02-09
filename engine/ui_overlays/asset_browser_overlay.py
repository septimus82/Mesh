"""Asset Browser Overlay."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
import engine.optional_arcade as optional_arcade

from ..text_draw import TextCache, draw_text_cached
from .common import UIElement, draw_panel_bg, _draw_rectangle_filled, _draw_lrtb_rectangle_outline

if TYPE_CHECKING:  # pragma: no cover
    from ..game import GameWindow


class AssetBrowserOverlay(UIElement):
    """Editor-only overlay for browsing assets."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self._text_cache = TextCache(max_size=128)

    def draw(self) -> None:
        controller = getattr(self.window, "editor_controller", None)
        if controller is None or not getattr(controller, "active", False):
            return
        if not getattr(controller, "asset_browser_active", False):
            return

        # Check dock tab visibility - Asset browser only visible if right dock is "Assets"
        dock = getattr(controller, "dock", None)
        snapshot = dock.get_snapshot() if dock is not None and hasattr(dock, "get_snapshot") else dock
        right_dock_tab = getattr(snapshot, "right_tab", "Inspector") or "Inspector"
        if right_dock_tab != "Assets":
            return

        # Dimensions
        win_w, win_h = self.window.width, self.window.height
        panel_w, panel_h = 900, 600
        
        left = (win_w - panel_w) // 2
        right = left + panel_w
        top = (win_h + panel_h) // 2
        bottom = top - panel_h
        
        # Ensure within bounds
        if top > win_h - 20: top = win_h - 20
        if bottom < 20: bottom = 20
        if left < 20: left = 20
        if right > win_w - 20: right = win_w - 20
        
        draw_panel_bg(left, right, bottom, top)
        
        # Header / Search
        header_h = 40
        search_y = top - header_h / 2 - 8
        search_rect_l = left + 20
        search_rect_r = right - 20
        
        from ..editor.panel_search_model import format_search_bar_text  # noqa: PLC0415

        search = getattr(controller, "search", None)
        filter_text = search.get_assets_search() if search is not None else ""
        kind_text = getattr(controller, "asset_browser_kind", "All")
        search_focused = bool(search is not None and search.is_panel_search_focused("assets"))

        draw_text_cached(
            format_search_bar_text(filter_text, search_focused),
            search_rect_l,
            search_y,
            color=(255, 255, 255),
            font_size=14,
            cache=self._text_cache,
        )
        draw_text_cached(f"Filter (Tab): {kind_text}", search_rect_r - 150, search_y, color=(100, 200, 255), font_size=14, cache=self._text_cache)
        
        _draw_lrtb_rectangle_outline(search_rect_l - 5, search_rect_r + 5, top - 5, top - header_h, (255, 255, 255, 50), 1)

        # Split Layout
        split_x = left + (right - left) * 0.6
        content_top = top - header_h - 10
        content_bottom = bottom + 10
        
        # Separator
        _draw_lrtb_rectangle_outline(split_x, split_x + 1, content_top, content_bottom, (255, 255, 255, 30), 1)
        
        # List View
        rows = getattr(controller, "_asset_browser_filtered_rows", [])
        sel_idx = getattr(controller, "asset_browser_selection_index", 0)
        
        line_height = 24
        visible_lines = max(0, int((content_top - content_bottom) / line_height) - 1)
        
        # Scroll logic
        scroll_offset = 0
        if sel_idx >= visible_lines:
             scroll_offset = sel_idx - visible_lines + 1
             
        start_idx = scroll_offset
        end_idx = min(len(rows), start_idx + visible_lines)
        
        current_y = content_top - line_height
        
        for i in range(start_idx, end_idx):
            row = rows[i]
            is_selected = (i == sel_idx)
            
            if is_selected:
                _draw_rectangle_filled(left + 10, split_x - 10, current_y - 4, current_y + 16, (255, 255, 255, 40))
                
            color = (255, 255, 255) if is_selected else (180, 180, 180)
            draw_text_cached(row.display_name, left + 15, current_y, color=color, font_size=12, cache=self._text_cache)
            draw_text_cached(row.kind, split_x - 50, current_y, color=(100, 100, 100), font_size=10, align="right", cache=self._text_cache)
            
            current_y -= line_height

        # Details Panel
        if 0 <= sel_idx < len(rows):
            sel_row = rows[sel_idx]
            detail_x = split_x + 20
            detail_y = content_top - 20
            
            draw_text_cached("DETAILS", detail_x, detail_y, color=(255, 200, 100), font_size=14, bold=True, cache=self._text_cache)
            detail_y -= 30
            
            draw_text_cached("Name:", detail_x, detail_y, color=(150, 150, 150), font_size=10, cache=self._text_cache)
            draw_text_cached(sel_row.display_name, detail_x, detail_y - 15, color=(255, 255, 255), font_size=12, cache=self._text_cache)
            detail_y -= 40
            
            draw_text_cached("Kind:", detail_x, detail_y, color=(150, 150, 150), font_size=10, cache=self._text_cache)
            draw_text_cached(sel_row.kind, detail_x, detail_y - 15, color=(255, 255, 255), font_size=12, cache=self._text_cache)
            detail_y -= 40
            
            draw_text_cached("Path:", detail_x, detail_y, color=(150, 150, 150), font_size=10, cache=self._text_cache)
            # Wrap path if needed? For now just draw
            draw_text_cached(sel_row.rel_path, detail_x, detail_y - 15, color=(100, 255, 100), font_size=10, cache=self._text_cache)
        else:
            search = getattr(controller, "search", None)
            filter_val = str(search.get_assets_search() if search is not None else "" or "")
            if not rows and filter_val:
                 draw_text_cached("No matches found.", split_x + 20, content_top - 20, color=(255, 100, 100), font_size=12, cache=self._text_cache)

