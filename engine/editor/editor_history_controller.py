from __future__ import annotations

from typing import Any

from engine.editor.undo_history_model import (
    clamp_history_cursor,
    compute_history_window,
    filter_undo_history_entries,
    resolve_jump_delta,
)
from engine.editor.editor_dock_query import get_dock_snapshot, get_effective_dock_widths


class EditorHistoryController:
    def __init__(self, editor: Any) -> None:
        self._editor = editor
        self._search_text = ""
        self._cursor_index = 0

    def get_search_text(self) -> str:
        return self._search_text

    def set_search_text(self, text: str) -> bool:
        value = str(text or "")
        if value == self._search_text:
            return False
        self._search_text = value
        return True

    def get_cursor_index(self) -> int:
        return self._cursor_index

    def set_cursor_index(self, value: int) -> None:
        self._cursor_index = int(value)

    def get_entries(self) -> list[Any]:
        entries: list[Any] = []
        undo_ctrl = getattr(self._editor, "undo", None)
        if undo_ctrl is not None and hasattr(undo_ctrl, "get_history_entries"):
            entries = undo_ctrl.get_history_entries()
        self._cursor_index = clamp_history_cursor(self._cursor_index, len(entries))
        return entries

    def get_filtered_entries(self) -> list[Any]:
        entries = self.get_entries()
        filtered = filter_undo_history_entries(entries, self._search_text)
        if filtered:
            if not any(entry.real_index == self._cursor_index for entry in filtered):
                self._cursor_index = filtered[0].real_index
        return filtered

    def on_open_tab(self) -> None:
        entries = self.get_entries()
        current = self._history_current_index(entries)
        if current >= 0:
            self._cursor_index = current

    def handle_input(self, key: int, modifiers: int) -> bool:  # noqa: ARG002
        if not getattr(self._editor, "active", False):
            return False
        snapshot = get_dock_snapshot(self._editor)
        if snapshot is None or snapshot.right_tab != "History":
            return False
        if self._history_input_blocked():
            return True

        entries = self.get_filtered_entries()
        count = len(entries)
        if count <= 0:
            return True

        cursor_display = self._history_display_index(entries)
        if key == self._key("UP"):
            new_index = max(0, cursor_display - 1)
            self._cursor_index = entries[new_index].real_index
            return True
        if key == self._key("DOWN"):
            new_index = min(count - 1, cursor_display + 1)
            self._cursor_index = entries[new_index].real_index
            return True
        if key in (self._key("ENTER"), self._key("RETURN")):
            if self._editor.search.is_panel_search_focused("history"):
                return True
            return self.jump_to(self._cursor_index)

        return False

    def handle_mouse_click(self, x: float, y: float, button: int) -> bool:
        if not getattr(self._editor, "active", False):
            return False
        snapshot = get_dock_snapshot(self._editor)
        if snapshot is None or snapshot.right_tab != "History":
            return False
        if self._history_input_blocked():
            return True
        if self._editor.search.is_panel_search_focused("history"):
            return True
        if button != self._mouse_button_left():
            return True

        entries = self.get_filtered_entries()
        if not entries:
            return True

        from engine.editor.editor_shell_layout import (  # noqa: PLC0415
            compute_editor_shell_layout,
            TAB_HEADER_HEIGHT,
        )
        from engine.editor.undo_history_model import HISTORY_LINE_HEIGHT, HISTORY_PADDING

        window = getattr(self._editor, "window", None)
        window_w = int(getattr(window, "width", 1280) or 1280)
        window_h = int(getattr(window, "height", 720) or 720)
        left_w, right_w = get_effective_dock_widths(self._editor, window_w)

        layout = compute_editor_shell_layout(window_w, window_h, left_w, right_w)
        dock_rect = layout.right_dock
        if not dock_rect.contains_point(x, y):
            return False

        content_top = dock_rect.top - TAB_HEADER_HEIGHT - HISTORY_PADDING - HISTORY_LINE_HEIGHT
        content_bottom = dock_rect.bottom + HISTORY_PADDING
        if y > content_top or y < content_bottom:
            return True

        cursor_display = self._history_display_index(entries)
        visible_capacity = int((content_top - content_bottom) / HISTORY_LINE_HEIGHT)
        start_idx, visible = compute_history_window(cursor_display, len(entries), visible_capacity)

        row_y = content_top
        for idx in range(start_idx, start_idx + visible):
            row_top = row_y
            row_bottom = row_y - HISTORY_LINE_HEIGHT
            if row_bottom <= y <= row_top:
                self._cursor_index = entries[idx].real_index
                self.jump_to(self._cursor_index)
                return True
            row_y -= HISTORY_LINE_HEIGHT

        return True

    def jump_to(self, cursor_index: int) -> bool:
        entries = self.get_entries()
        count = len(entries)
        if count <= 0:
            return False

        cursor_index = clamp_history_cursor(cursor_index, count)
        delta = resolve_jump_delta(entries, cursor_index)
        if delta == 0:
            return False
        self._jump_by_delta(delta)

        entries = self.get_entries()
        current = self._history_current_index(entries)
        if current >= 0:
            self._cursor_index = current
        return True

    def _jump_by_delta(self, delta: int) -> None:
        if delta == 0:
            return
        if delta < 0:
            for _ in range(abs(delta)):
                self._editor.undo_last()
        else:
            for _ in range(delta):
                self._editor.redo_last()

    def _history_input_blocked(self) -> bool:
        from engine.editor_tooltips_model import (  # noqa: PLC0415
            _is_modal_open_state,
            _is_text_input_active_state,
        )
        from engine.editor.editor_panels_query import panels_is_open  # noqa: PLC0415

        if panels_is_open(self._editor, "unsaved_confirm"):
            return True
        if self._editor.search.is_panel_search_focused("history"):
            return _is_modal_open_state(self._editor)
        return _is_text_input_active_state(self._editor) or _is_modal_open_state(self._editor)

    def _history_current_index(self, entries: list[Any]) -> int:
        for i, entry in enumerate(entries):
            if getattr(entry, "is_current", False):
                return int(getattr(entry, "real_index", i))
        return -1

    def _history_display_index(self, entries: list[Any]) -> int:
        if not entries:
            return 0
        for i, entry in enumerate(entries):
            if getattr(entry, "real_index", None) == self._cursor_index:
                return i
        return 0

    def _key(self, name: str) -> int:
        from engine import optional_arcade  # noqa: PLC0415

        return int(getattr(optional_arcade.arcade.key, name))

    def _mouse_button_left(self) -> int:
        from engine import optional_arcade  # noqa: PLC0415

        return int(optional_arcade.arcade.MOUSE_BUTTON_LEFT)
