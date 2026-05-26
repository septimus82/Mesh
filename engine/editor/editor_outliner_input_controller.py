from __future__ import annotations

from typing import Any

import engine.optional_arcade as optional_arcade


class EditorOutlinerInputController:
    """Mouse input routing for Outliner dock content."""

    def __init__(self, editor: Any) -> None:
        self._editor = editor

    def handle_mouse_click(self, x: float, y: float, button: int) -> bool:
        editor = self._editor
        if not getattr(editor, "active", False):
            return False
        if not getattr(editor, "entity_panels_active", False):
            return False
        if not self._is_outliner_tab():
            return False

        dock = self._left_dock()
        if dock is None or not dock.contains_point(float(x), float(y)):
            return False
        if button != optional_arcade.arcade.MOUSE_BUTTON_LEFT:
            return True

        row = self._outliner_row_at(float(x), float(y))
        if row is None:
            return True

        editor.entity_panels_selection_index = int(row)
        selector = getattr(editor, "_entity_panels_select_current", None)
        if callable(selector):
            selector()
            self._clear_panel_selection_drag_state()
        return True

    def _is_outliner_tab(self) -> bool:
        dock = getattr(self._editor, "dock", None)
        snapshot = dock.get_snapshot() if dock is not None and hasattr(dock, "get_snapshot") else dock
        return (getattr(snapshot, "left_tab", "Outliner") or "Outliner") == "Outliner"

    def _left_dock(self) -> Any | None:
        from engine.editor.editor_dock_query import get_effective_dock_widths
        from engine.editor.editor_shell_layout import compute_editor_shell_layout

        window = getattr(self._editor, "window", None)
        window_w = int(getattr(window, "width", 1280) or 1280)
        window_h = int(getattr(window, "height", 720) or 720)
        left_w, right_w = get_effective_dock_widths(self._editor, window_w)
        return compute_editor_shell_layout(window_w, window_h, left_w, right_w).left_dock

    def _outliner_row_at(self, x: float, y: float) -> int | None:
        from engine.editor.editor_shell_layout import TAB_HEADER_HEIGHT

        dock = self._left_dock()
        if dock is None:
            return None
        content_left = dock.left + 8.0
        content_right = dock.right - 8.0
        if not content_left <= x <= content_right:
            return None

        refresh = getattr(self._editor, "_refresh_entity_panels_list", None)
        if callable(refresh):
            refresh()
        items = list(getattr(self._editor, "_cached_entity_panels_list", []) or [])
        if not items:
            return None

        cursor_index = int(getattr(self._editor, "entity_panels_selection_index", 0) or 0)
        max_visible = 19
        start_idx = 0
        if cursor_index > max_visible / 2:
            start_idx = max(0, int(cursor_index - max_visible / 2))
        end_idx = min(len(items), start_idx + max_visible)
        visible_count = max(0, end_idx - start_idx)
        if visible_count <= 0:
            return None

        line_height = 18.0
        first_item_line = 4
        start_y = dock.top - TAB_HEADER_HEIGHT - 8.0
        for local_index in range(visible_count):
            line_index = first_item_line + local_index
            row_top = start_y - (float(line_index) * line_height)
            row_bottom = row_top - line_height
            if row_bottom <= y <= row_top:
                return start_idx + local_index
        return None

    def _clear_panel_selection_drag_state(self) -> None:
        editor = self._editor
        editor.entity_dragging = False
        editor.entity_drag_start_pos = None
        editor._multiselect_drag_starts = {}
        editor._move_preview_delta_xy = None
        editor._transform_snap_active = False
        editor._rotate_drag_active = False
        editor._scale_drag_active = False
        editor._transform_drag_pivot = None
        editor._transform_drag_mouse_start = None
        editor._transform_drag_start_rots = {}
        editor._transform_drag_start_scales = {}
