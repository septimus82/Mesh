"""Undo History overlay for editor right dock."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..text_draw import draw_text_cached, TextCache
from .common import UIElement, _draw_rectangle_filled
from ..editor.editor_shell_layout import (
    compute_editor_shell_layout,
    TAB_HEADER_HEIGHT,
)
from ..editor.undo_history_model import (
    HISTORY_LINE_HEIGHT,
    HISTORY_PADDING,
    build_undo_history_entries,
    compute_history_window,
    filter_undo_history_entries,
)
from ..editor.panel_search_model import format_search_bar_text

if TYPE_CHECKING:  # pragma: no cover
    from ..game import GameWindow


HISTORY_TEXT_COLOR = (220, 220, 230, 255)
HISTORY_DIM_COLOR = (150, 150, 160, 255)
HISTORY_CURRENT_BG = (70, 110, 150, 80)
HISTORY_CURSOR_BG = (90, 140, 200, 140)


class UndoHistoryOverlay(UIElement):
    """Editor-only overlay that draws the undo history list."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self._text_cache = TextCache(max_size=128)

    def draw(self) -> None:
        controller = getattr(self.window, "editor_controller", None)
        if controller is None or not getattr(controller, "active", False):
            return

        right_tab = getattr(controller, "_right_dock_tab", "Inspector")
        if right_tab != "History":
            return

        # Layout
        window_w = int(getattr(self.window, "width", 1280) or 1280)
        window_h = int(getattr(self.window, "height", 720) or 720)

        getter = getattr(controller, "get_effective_dock_widths", None)
        if callable(getter):
            left_w, right_w = getter(window_w)
        else:
            left_w = getattr(controller, "_dock_left_w", 320)
            right_w = getattr(controller, "_dock_right_w", 320)

        layout = compute_editor_shell_layout(window_w, window_h, left_w, right_w)
        dock = layout.right_dock

        getter = getattr(controller, "get_filtered_undo_history_entries", None)
        if callable(getter):
            entries = getter()
        else:
            base_entries = build_undo_history_entries(
                getattr(controller, "undo_stack", []),
                getattr(controller, "redo_stack", []),
            )
            search_text = getattr(controller, "_history_search", "")
            entries = filter_undo_history_entries(base_entries, search_text)

        search_text = getattr(controller, "_history_search", "")
        search_focused = getattr(controller, "_search_focus", None) == "history"
        search_line = format_search_bar_text(search_text, search_focused)

        content_top = dock.top - TAB_HEADER_HEIGHT - HISTORY_PADDING
        draw_text_cached(
            search_line,
            dock.left + HISTORY_PADDING,
            content_top - HISTORY_LINE_HEIGHT + 2,
            color=HISTORY_TEXT_COLOR,
            font_size=11,
            cache=self._text_cache,
        )
        content_top -= HISTORY_LINE_HEIGHT

        if not entries:
            draw_text_cached(
                "No history",
                dock.left + HISTORY_PADDING,
                content_top - HISTORY_LINE_HEIGHT,
                color=HISTORY_DIM_COLOR,
                font_size=11,
                cache=self._text_cache,
            )
            return

        cursor_real = int(getattr(controller, "_history_cursor_index", 0) or 0)

        content_bottom = dock.bottom + HISTORY_PADDING
        visible_capacity = int((content_top - content_bottom) / HISTORY_LINE_HEIGHT)
        cursor_display = _resolve_cursor_display_index(entries, cursor_real)
        start_idx, visible = compute_history_window(cursor_display, len(entries), visible_capacity)

        y = content_top
        for idx in range(start_idx, start_idx + visible):
            entry = entries[idx]
            row_top = y
            row_bottom = y - HISTORY_LINE_HEIGHT

            if entry.is_current:
                _draw_rectangle_filled(
                    dock.left + HISTORY_PADDING,
                    dock.right - HISTORY_PADDING,
                    row_bottom,
                    row_top,
                    HISTORY_CURRENT_BG,
                )
            if idx == cursor_display:
                _draw_rectangle_filled(
                    dock.left + HISTORY_PADDING,
                    dock.right - HISTORY_PADDING,
                    row_bottom,
                    row_top,
                    HISTORY_CURSOR_BG,
                )

            label = f"{entry.index:02d} {entry.label}"
            draw_text_cached(
                label,
                dock.left + HISTORY_PADDING + 4,
                row_bottom + 2,
                color=HISTORY_TEXT_COLOR,
                font_size=11,
                cache=self._text_cache,
            )

            y -= HISTORY_LINE_HEIGHT

            if y < content_bottom:
                break


def _resolve_cursor_display_index(entries: list[Any], cursor_real: int) -> int:
    if not entries:
        return 0
    for idx, entry in enumerate(entries):
        if getattr(entry, "real_index", None) == cursor_real:
            return idx
    return 0
