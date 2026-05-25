"""Undo History overlay for editor right dock."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
import engine.optional_arcade as optional_arcade

from ..text_draw import draw_text_cached, TextCache
from .common import UIElement, _draw_rectangle_filled, _draw_tb_rectangle_outline
from .widgets import Rect, ScrollList

if TYPE_CHECKING:  # pragma: no cover
    from ..game import GameWindow


HISTORY_TEXT_COLOR = (220, 220, 230, 255)
HISTORY_DIM_COLOR = (150, 150, 160, 255)
HISTORY_CURRENT_BG = (70, 110, 150, 80)
HISTORY_CURSOR_BG = (90, 140, 200, 140)
_DEFAULT_HISTORY_ROW_HEIGHT = 18


class UndoHistoryOverlay(UIElement):
    """Editor-only overlay that draws the undo history list."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self._text_cache = TextCache(max_size=128)
        self._scroll_list = ScrollList(items=[], row_height=_DEFAULT_HISTORY_ROW_HEIGHT, selected_index=0, scroll_offset=0.0)
        self._scroll_user_override = False
        self._last_history_entries: list[Any] = []
        self._history_list_rect: Rect | None = None

    def draw(self) -> None:
        from ..editor.editor_dock_query import get_effective_dock_widths
        from ..editor.editor_shell_layout import (
            TAB_HEADER_HEIGHT,
            compute_editor_shell_layout,
        )
        from ..editor.panel_search_model import format_search_bar_text
        from ..editor.undo_history_model import (
            HISTORY_LINE_HEIGHT,
            HISTORY_PADDING,
            compute_history_window,
            filter_undo_history_entries,
        )

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
        _draw_tb_rectangle_outline(
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
        auto_start_idx, _auto_visible = compute_history_window(cursor_display, len(entries), visible_capacity)

        list_bounds = Rect(
            x=dock.left + HISTORY_PADDING,
            y=content_bottom,
            width=max(0.0, (dock.right - dock.left) - (2 * HISTORY_PADDING)),
            height=max(0.0, content_top - content_bottom),
        )
        self._history_list_rect = list_bounds
        self._last_history_entries = list(entries)
        self._scroll_list.items = [f"{entry.index:02d} {entry.label}" for entry in entries]
        self._scroll_list.row_height = int(max(1, round(HISTORY_LINE_HEIGHT)))
        if not self._scroll_user_override:
            self._scroll_list.scroll_offset = float(auto_start_idx)
        self._scroll_list.selected_index = int(cursor_display)
        list_layout = self._scroll_list.layout(list_bounds)

        left_pad = HISTORY_PADDING + 4
        right_pad = HISTORY_PADDING + 6
        right_gutter = 60
        approx_char_w = max(1.0, 11 * 0.6)
        for instruction in list_layout.instructions:
            kind = str(instruction.kind or "")
            payload = instruction.payload if isinstance(instruction.payload, dict) else {}
            if kind == "scroll_row_bg":
                rect = payload.get("rect")
                row_idx = payload.get("row_index")
                if not isinstance(rect, Rect) or not isinstance(row_idx, int):
                    continue
                if row_idx < 0 or row_idx >= len(entries):
                    continue
                entry = entries[row_idx]
                if entry.is_current:
                    _draw_rectangle_filled(rect.left, rect.right, rect.bottom, rect.top, HISTORY_CURRENT_BG)
                if bool(payload.get("selected", False)):
                    _draw_rectangle_filled(rect.left, rect.right, rect.bottom, rect.top, HISTORY_CURSOR_BG)
                continue
            if kind == "scroll_row_text":
                rect = payload.get("rect")
                row_idx = payload.get("row_index")
                if not isinstance(rect, Rect) or not isinstance(row_idx, int):
                    continue
                if row_idx < 0 or row_idx >= len(entries):
                    continue
                entry = entries[row_idx]
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
                    rect.bottom + 2,
                    color=HISTORY_TEXT_COLOR,
                    font_size=11,
                    cache=self._text_cache,
                )
                draw_text_cached(
                    f"{entry.index:02d}",
                    dock.right - right_pad,
                    rect.bottom + 2,
                    color=HISTORY_DIM_COLOR,
                    font_size=10,
                    anchor_x="right",
                    cache=self._text_cache,
                )

        # Scrollbar (render-only, if scrollable)
        visible = self._scroll_list.visible_count
        start_idx = self._scroll_list.visible_start_index
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

    def _is_history_tab_active(self) -> bool:
        controller = getattr(self.window, "editor_controller", None)
        if controller is None or not getattr(controller, "active", False):
            return False
        dock_ctl = getattr(controller, "dock", None)
        snapshot = dock_ctl.get_snapshot() if dock_ctl is not None and hasattr(dock_ctl, "get_snapshot") else dock_ctl
        right_tab = getattr(snapshot, "right_tab", "Inspector") or "Inspector"
        return str(right_tab) == "History"

    def on_mouse_scroll(self, x: float, y: float, scroll_x: float, scroll_y: float) -> bool:  # noqa: ARG002
        if not self._is_history_tab_active():
            return False
        bounds = self._history_list_rect
        if bounds is None or not bounds.contains(float(x), float(y)):
            return False
        changed = self._scroll_list.on_mouse_wheel(float(scroll_y))
        if changed:
            self._scroll_user_override = True
        return bool(changed)

    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int = 0) -> bool:  # noqa: ARG002
        if not self._is_history_tab_active():
            return False
        if int(button) != int(optional_arcade.arcade.MOUSE_BUTTON_LEFT):
            return False
        bounds = self._history_list_rect
        if bounds is None or not bounds.contains(float(x), float(y)):
            return False
        if not self._scroll_list.on_mouse_press(float(x), float(y)):
            return False
        self._scroll_user_override = True
        selected_index = int(self._scroll_list.selected_index)
        if selected_index < 0 or selected_index >= len(self._last_history_entries):
            return True
        entry = self._last_history_entries[selected_index]
        controller = getattr(self.window, "editor_controller", None)
        history_ctl = getattr(controller, "history", None) if controller is not None else None
        jump = getattr(history_ctl, "jump_to", None) if history_ctl is not None else None
        if callable(jump):
            try:
                jump(int(getattr(entry, "real_index", 0)))
            except Exception:
                return True
        return True


def _resolve_cursor_display_index(entries: list[Any], cursor_real: int) -> int:
    if not entries:
        return 0
    for idx, entry in enumerate(entries):
        if getattr(entry, "real_index", None) == cursor_real:
            return idx
    return 0
