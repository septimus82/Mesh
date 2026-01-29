"""Project Explorer overlay for editor left dock."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from ..text_draw import TextCache, draw_text_cached
from .common import UIElement, _draw_rectangle_filled, _draw_lrtb_rectangle_outline
from ..editor.editor_shell_layout import compute_editor_shell_layout
from ..editor.panel_search_model import format_search_bar_text
from .providers import project_explorer_provider
from ..editor.project_explorer_model import (
    PROJECT_LINE_HEIGHT,
    compute_project_explorer_layout,
    compute_project_window,
    display_index_from_selectable_index,
    format_project_action_label,
    format_project_recent_label,
    format_project_row_label,
)

if TYPE_CHECKING:  # pragma: no cover
    from ..game import GameWindow


PROJECT_TEXT_COLOR = (220, 220, 230, 255)
PROJECT_DIM_COLOR = (150, 150, 160, 255)
PROJECT_SELECTED_BG = (90, 140, 200, 140)
PROJECT_RENAME_BG = (40, 40, 50, 255)
PROJECT_RENAME_BORDER = (120, 160, 220, 255)
PROJECT_RENAME_CURSOR = (220, 220, 230, 255)


class ProjectExplorerOverlay(UIElement):
    """Editor-only overlay for the Project Explorer panel."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self._text_cache = TextCache(max_size=256)

    def _get_inline_rename_info(self, controller: object) -> tuple[bool, Optional[str], Optional[str], int, int, int]:
        """Get inline rename state from controller.
        
        Returns:
            Tuple of (is_active, display_text, original_path, cursor_pos, sel_start, sel_end).
            cursor_pos is the caret position within the stem text.
            sel_start/sel_end are selection bounds within the stem text.
        """
        project_ctrl = getattr(controller, "project_explorer", None)
        if project_ctrl is None:
            return (False, None, None, 0, 0, 0)
        if not getattr(project_ctrl, "inline_rename_active", False):
            return (False, None, None, 0, 0, 0)
        display_text = None
        original_path = None
        cursor_pos = 0
        sel_start = 0
        sel_end = 0
        getter = getattr(project_ctrl, "get_rename_display_text", None)
        if callable(getter):
            display_text = getter()
        path_getter = getattr(project_ctrl, "get_rename_original_path", None)
        if callable(path_getter):
            original_path = path_getter()
        # Get cursor/selection from inline_rename_state
        state = getattr(project_ctrl, "inline_rename_state", None)
        if state is not None:
            sel_start = getattr(state, "selection_start", 0)
            sel_end = getattr(state, "selection_end", 0)
            cursor_pos = sel_end  # Caret is always at selection_end
        return (True, display_text, original_path, cursor_pos, sel_start, sel_end)

    def draw(self) -> None:
        controller = getattr(self.window, "editor_controller", None)
        if controller is None or not getattr(controller, "active", False):
            return

        left_tab = getattr(controller, "_left_dock_tab", "Outliner")
        if left_tab != "Project":
            return

        window_w = int(getattr(self.window, "width", 1280) or 1280)
        window_h = int(getattr(self.window, "height", 720) or 720)
        getter = getattr(controller, "get_effective_dock_widths", None)
        if callable(getter):
            left_w, right_w = getter(window_w)
        else:
            left_w = getattr(controller, "_dock_left_w", 320)
            right_w = getattr(controller, "_dock_right_w", 320)

        layout = compute_editor_shell_layout(window_w, window_h, left_w, right_w)
        dock = layout.left_dock
        panel = compute_project_explorer_layout(dock)

        # Use new provider
        # Note: We let the provider handle windowing if it wants, but we need to compute viewport height for it.
        viewport_h = int(panel.list_rect.height)
        data = project_explorer_provider(self.window, viewport_h, PROJECT_LINE_HEIGHT, overscan=5)
        
        rows = data.get("rows", [])
        search_text = str(data.get("search_query", ""))
        search_focused = getattr(controller, "_search_focus", None) == "project"
        
        # Get inline rename state
        rename_active, rename_text, rename_path, rename_cursor, rename_sel_start, rename_sel_end = self._get_inline_rename_info(controller)
        
        # Selection logic:
        # The data returns 'selected_index' which is index in 'selectable_rows'.
        # We need to map it to display rows if we are just rendering display rows.
        # But 'rows' returned by provider are ALREADY WINDOWED?
        # Let's check get_provider_payload implementation:
        # returns "rows": visible_rows (windowed), "selectable_rows": self.selectable_rows, "selected_index": self.selected_index
        
        # Search line
        search_line = format_search_bar_text(search_text, search_focused)
        draw_text_cached(
            search_line,
            panel.search_rect.left,
            panel.search_rect.bottom + 2,
            color=PROJECT_TEXT_COLOR,
            font_size=11,
            cache=self._text_cache,
        )

        total_count = data.get("total_count", 0)
        # If no items at all (not even scrolled out of view)
        if not rows and total_count == 0:
            draw_text_cached(
                "No project items",
                panel.list_rect.left,
                panel.list_rect.top - PROJECT_LINE_HEIGHT + 2,
                color=PROJECT_DIM_COLOR,
                font_size=11,
                cache=self._text_cache,
            )
            return

        # Render windowed rows
        start_idx = data.get("start_index", 0)
        scroll_y = data.get("scroll_y", 0)
        selected_row_id = data.get("selected_row_id")
        selected_row_ids = set(data.get("selected_row_ids", []) or [])
        has_multi = bool(data.get("has_multi", False))

        for idx, row in enumerate(rows):
            real_index = start_idx + idx
            
            # Position Y:
            # y = Top - (index * h) + scroll_y
            y_pos = panel.list_rect.top - (real_index * PROJECT_LINE_HEIGHT) + scroll_y
            row_top = y_pos
            row_bottom = y_pos - PROJECT_LINE_HEIGHT
            
            # Simple culling for safety (though provider should handle it)
            if row_bottom > panel.list_rect.top:
                continue
            if row_top < panel.list_rect.bottom:
                continue

            # Check if this row is being renamed
            is_rename_row = False
            if rename_active and rename_path and row.entry is not None:
                row_path = str(getattr(row.entry, "rel_path", ""))
                if row_path == rename_path:
                    is_rename_row = True

            if is_rename_row:
                # Draw inline rename editor
                self._draw_inline_rename(
                    panel.list_rect.left,
                    panel.list_rect.right,
                    row_bottom,
                    row_top,
                    rename_text or "",
                    rename_cursor,
                    rename_sel_start,
                    rename_sel_end,
                )
                continue

            if selected_row_ids and id(row) in selected_row_ids:
                _draw_rectangle_filled(
                    panel.list_rect.left,
                    panel.list_rect.right,
                    row_bottom,
                    row_top,
                    PROJECT_SELECTED_BG,
                )
                if has_multi and selected_row_id is not None and id(row) == selected_row_id:
                    _draw_lrtb_rectangle_outline(
                        panel.list_rect.left,
                        panel.list_rect.right,
                        row_top,
                        row_bottom,
                        PROJECT_RENAME_BORDER,
                        1,
                    )
            elif selected_row_id is not None and id(row) == selected_row_id:
                _draw_rectangle_filled(
                    panel.list_rect.left,
                    panel.list_rect.right,
                    row_bottom,
                    row_top,
                    PROJECT_SELECTED_BG,
                )

            if row.kind == "header":
                label = str(row.header or "")
                color = PROJECT_DIM_COLOR
            elif row.kind == "action":
                label = format_project_action_label(row)
                color = PROJECT_TEXT_COLOR if getattr(row, "enabled", True) else PROJECT_DIM_COLOR
            elif row.recent is not None:
                label = format_project_recent_label(row.recent)
                color = PROJECT_TEXT_COLOR
            else:
                label = format_project_row_label(row.entry)
                color = PROJECT_TEXT_COLOR # format_project_row_label already handles some formatting?
            
            draw_text_cached(
                label,
                panel.list_rect.left + 2,
                row_bottom + 2,
                color=color,
                font_size=11,
                cache=self._text_cache,
            )

    def _draw_inline_rename(
        self,
        left: float,
        right: float,
        bottom: float,
        top: float,
        text: str,
        cursor_pos: int = 0,
        sel_start: int = 0,
        sel_end: int = 0,
    ) -> None:
        """Draw the inline rename text editor.
        
        Args:
            left: Left edge of the row.
            right: Right edge of the row.
            bottom: Bottom edge of the row.
            top: Top edge of the row.
            text: The current rename text (stem + extension).
            cursor_pos: Caret position within the stem (before extension).
            sel_start: Selection start within the stem.
            sel_end: Selection end within the stem.
        """
        # Background
        _draw_rectangle_filled(left, right, bottom, top, PROJECT_RENAME_BG)
        
        # Border
        _draw_lrtb_rectangle_outline(left, right, top, bottom, PROJECT_RENAME_BORDER, 1)
        
        # Approximate character width for monospace font at size 11
        CHAR_WIDTH = 7.0
        TEXT_OFFSET = 2
        
        # Draw selection highlight if there is a selection
        if sel_start != sel_end and sel_start < sel_end:
            sel_left = left + TEXT_OFFSET + sel_start * CHAR_WIDTH
            sel_right = left + TEXT_OFFSET + sel_end * CHAR_WIDTH
            # Clamp to bounds
            sel_left = max(sel_left, left + TEXT_OFFSET)
            sel_right = min(sel_right, right - TEXT_OFFSET)
            if sel_right > sel_left:
                _draw_rectangle_filled(
                    sel_left,
                    sel_right,
                    bottom,
                    top,
                    (80, 120, 180, 128),  # Selection highlight color
                )
        
        # Draw cursor (blinking)
        import time
        blink = int(time.time() * 2) % 2 == 0
        if blink:
            cursor_x = left + TEXT_OFFSET + cursor_pos * CHAR_WIDTH
            # Draw cursor line
            _draw_lrtb_rectangle_outline(
                cursor_x - 0.5,
                cursor_x + 0.5,
                top - 2,
                bottom + 2,
                PROJECT_TEXT_COLOR,
                1,
            )
        
        # Draw text
        draw_text_cached(
            text,
            left + TEXT_OFFSET,
            bottom + 2,
            color=PROJECT_TEXT_COLOR,
            font_size=11,
            cache=self._text_cache,
        )
