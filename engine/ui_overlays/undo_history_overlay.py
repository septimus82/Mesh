"""Undo History overlay for editor right dock."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..text_draw import draw_text_cached, TextCache
from .common import UIElement, _draw_rectangle_filled, _draw_lrtb_rectangle_outline
from ..editor.editor_shell_layout import (
    compute_editor_shell_layout,
    TAB_HEADER_HEIGHT,
)
from ..editor.editor_dock_query import get_effective_dock_widths
from ..editor.undo_history_model import (
    HISTORY_LINE_HEIGHT,
    HISTORY_PADDING,
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

        dock_ctl = getattr(controller, "dock", None)
        snapshot = dock_ctl.get_snapshot() if dock_ctl is not None and hasattr(dock_ctl, "get_snapshot") else dock_ctl
        right_tab = getattr(snapshot, "right_tab", "Inspector") or "Inspector"
        if right_tab != "History":
            return

        # Layout
        window_w = int(getattr(self.window, "width", 1280) or 1280)
        window_h = int(getattr(self.window, "height", 720) or 720)

        left_w, right_w = get_effective_dock_widths(controller, window_w)

        layout = compute_editor_shell_layout(window_w, window_h, left_w, right_w)
        dock = layout.right_dock

        getter = getattr(controller, "get_filtered_undo_history_entries", None)
        if callable(getter):
            entries = getter()
        else:
            undo_ctrl = getattr(controller, "undo", None)
            if undo_ctrl is not None and hasattr(undo_ctrl, "get_history_entries"):
                base_entries = undo_ctrl.get_history_entries()
                history_ctl = getattr(controller, "history", None)
                search_text = history_ctl.get_search_text() if history_ctl is not None else ""
                entries = filter_undo_history_entries(base_entries, search_text)
            else:
                entries = []

        history_ctl = getattr(controller, "history", None)
        search_text = history_ctl.get_search_text() if history_ctl is not None else ""
        search = getattr(controller, "search", None)
        search_focused = bool(search is not None and search.is_panel_search_focused("history"))
        search_line = format_search_bar_text(search_text, search_focused)

        # Panel framing
        _draw_rectangle_filled(
            dock.left,
            dock.right,
            dock.bottom,
            dock.top,
            (18, 18, 22, 220),
        )
        _draw_lrtb_rectangle_outline(
            dock.left,
            dock.right,
            dock.top,
            dock.bottom,
            (100, 100, 110, 255),
            1,
        )

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

        cursor_real = int(history_ctl.get_cursor_index() if history_ctl is not None else 0)

        content_bottom = dock.bottom + HISTORY_PADDING
        visible_capacity = int((content_top - content_bottom) / HISTORY_LINE_HEIGHT)
        cursor_display = _resolve_cursor_display_index(entries, cursor_real)
        start_idx, visible = compute_history_window(cursor_display, len(entries), visible_capacity)

        y = content_top
        left_pad = HISTORY_PADDING + 4
        right_pad = HISTORY_PADDING + 6
        right_gutter = 60
        approx_char_w = max(1.0, 11 * 0.6)
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
            max_label_w = max(0.0, (dock.right - right_gutter) - (dock.left + left_pad))
            max_label_chars = int(max_label_w / approx_char_w) if max_label_w > 0 else 0
            if max_label_chars > 0 and len(label) > max_label_chars:
                if max_label_chars >= 3:
                    label = label[: max(0, max_label_chars - 3)] + "..."
                else:
                    label = label[:max_label_chars]
            draw_text_cached(
                label,
                dock.left + left_pad,
                row_bottom + 2,
                color=HISTORY_TEXT_COLOR,
                font_size=11,
                cache=self._text_cache,
            )
            draw_text_cached(
                f"{entry.index:02d}",
                dock.right - right_pad,
                row_bottom + 2,
                color=HISTORY_DIM_COLOR,
                font_size=10,
                anchor_x="right",
                cache=self._text_cache,
            )

            y -= HISTORY_LINE_HEIGHT

            if y < content_bottom:
                break

        # Scrollbar (render-only, if scrollable)
        if entries and visible > 0 and len(entries) > visible:
            total_n = len(entries)
            visible_n = visible
            start_n = start_idx
            track_left = dock.right - HISTORY_PADDING - 3
            track_right = dock.right - HISTORY_PADDING - 1
            track_top = content_top
            track_bottom = content_bottom
            _draw_rectangle_filled(track_left, track_right, track_bottom, track_top, (90, 90, 100, 140))
            track_h = max(1.0, track_top - track_bottom)
            ratio = max(0.0, min(1.0, start_n / max(1, (total_n - visible_n))))
            thumb_h = max(10.0, track_h * (visible_n / total_n))
            usable_h = max(1.0, track_h - thumb_h)
            thumb_top = track_top - (ratio * usable_h)
            thumb_bottom = thumb_top - thumb_h
            _draw_rectangle_filled(track_left, track_right, thumb_bottom, thumb_top, (150, 150, 160, 200))

        # Optional footer hint
        if entries and visible > 0:
            total_n = len(entries)
            start_n = start_idx
            a = start_n + 1
            b = min(total_n, start_n + visible)
            hint = f"History {a}-{b} / {total_n}"
            draw_text_cached(
                hint,
                dock.right - HISTORY_PADDING,
                dock.bottom + HISTORY_PADDING - 2,
                color=HISTORY_DIM_COLOR,
                font_size=10,
                anchor_x="right",
                cache=self._text_cache,
            )


def _resolve_cursor_display_index(entries: list[Any], cursor_real: int) -> int:
    if not entries:
        return 0
    for idx, entry in enumerate(entries):
        if getattr(entry, "real_index", None) == cursor_real:
            return idx
    return 0
