"""Project Explorer overlay for editor left dock."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from ..text_draw import TextCache, draw_text_cached
from .common import UIElement, _draw_rectangle_filled, _draw_tb_rectangle_outline
from .providers import project_explorer_provider
from .theme import EDITOR_THEME
from .widgets import Rect, ScrollList

if TYPE_CHECKING:  # pragma: no cover
    from ..game import GameWindow


PROJECT_TEXT_COLOR = EDITOR_THEME.text_primary
PROJECT_DIM_COLOR = EDITOR_THEME.text_dim
PROJECT_SELECTED_BG = EDITOR_THEME.selected_row_bg
PROJECT_RENAME_BG = EDITOR_THEME.tree_bg
PROJECT_RENAME_BORDER = EDITOR_THEME.tree_accent
PROJECT_RENAME_CURSOR = EDITOR_THEME.text_primary


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
        from ..editor.editor_dock_query import get_effective_dock_widths
        from ..editor.editor_shell_layout import compute_editor_shell_layout
        from ..editor.panel_search_model import format_search_bar_text
        from ..editor.project_explorer_model import (
            PROJECT_LINE_HEIGHT,
            compute_project_explorer_layout,
            format_project_action_label,
            format_project_recent_label,
            format_project_row_label,
        )

        controller = getattr(self.window, "editor_controller", None)
        if controller is None or not getattr(controller, "active", False):
            return

        dock = getattr(controller, "dock", None)
        snapshot = dock.get_snapshot() if dock is not None and hasattr(dock, "get_snapshot") else dock
        left_tab = getattr(snapshot, "left_tab", "Outliner") or "Outliner"
        if left_tab != "Project":
            return

        window_w = int(getattr(self.window, "width", 1280) or 1280)
        window_h = int(getattr(self.window, "height", 720) or 720)
        left_w, right_w = get_effective_dock_widths(controller, window_w)

        layout = compute_editor_shell_layout(window_w, window_h, left_w, right_w)
        dock = layout.left_dock
        panel = compute_project_explorer_layout(dock)

        # Use new provider
        # Note: We let the provider handle windowing if it wants, but we need to compute viewport height for it.
        viewport_h = int(panel.list_rect.height)
        data = project_explorer_provider(self.window, viewport_h, PROJECT_LINE_HEIGHT, overscan=5)

        rows = data.get("rows", [])
        search_text = str(data.get("search_query", ""))
        search = getattr(controller, "search", None)
        search_focused = bool(search is not None and search.is_panel_search_focused("project"))

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

        # Render rows through shared ScrollList windowing mechanics.
        start_idx = int(data.get("start_index", 0) or 0)
        scroll_y = float(data.get("scroll_y", 0.0) or 0.0)
        selected_row_id = data.get("selected_row_id")
        selected_row_ids = set(data.get("selected_row_ids", []) or [])
        has_multi = bool(data.get("has_multi", False))
        scroll_list = _build_project_explorer_scrolllist(
            rows=list(rows),
            panel_list_rect=Rect(
                x=float(panel.list_rect.left),
                y=float(panel.list_rect.bottom),
                width=float(panel.list_rect.right - panel.list_rect.left),
                height=float(panel.list_rect.top - panel.list_rect.bottom),
            ),
            row_height=PROJECT_LINE_HEIGHT,
            start_index=start_idx,
            scroll_y=scroll_y,
            selected_row_id=selected_row_id,
            format_project_action_label=format_project_action_label,
            format_project_recent_label=format_project_recent_label,
            format_project_row_label=format_project_row_label,
        )

        self._draw_project_explorer_row_list(
            rows=list(rows),
            scroll_list=scroll_list,
            panel_list_rect=panel.list_rect,
            selected_row_id=selected_row_id,
            selected_row_ids=selected_row_ids,
            has_multi=has_multi,
            rename_active=rename_active,
            rename_path=rename_path,
            rename_text=rename_text or "",
            rename_cursor=rename_cursor,
            rename_sel_start=rename_sel_start,
            rename_sel_end=rename_sel_end,
            format_project_action_label=format_project_action_label,
            format_project_recent_label=format_project_recent_label,
            format_project_row_label=format_project_row_label,
        )

    def _draw_project_explorer_row_list(
        self,
        *,
        rows: list[Any],
        scroll_list: ScrollList,
        panel_list_rect: Any,
        selected_row_id: Any,
        selected_row_ids: set[Any],
        has_multi: bool,
        rename_active: bool,
        rename_path: str | None,
        rename_text: str,
        rename_cursor: int,
        rename_sel_start: int,
        rename_sel_end: int,
        format_project_action_label: Any,
        format_project_recent_label: Any,
        format_project_row_label: Any,
    ) -> None:
        from ..editor.project_explorer.project_explorer_model import PROJECT_LINE_HEIGHT  # noqa: PLC0415
        from ..editor.widgets.panel_primitives import EditorPanelBase, PanelField, PanelRow

        for row_index, _row_text, row_rect, _is_selected in scroll_list.visible_rows:
            row_data = rows[row_index]
            row_top = row_rect.top
            row_bottom = row_rect.bottom

            is_rename_row = False
            if rename_active and rename_path and row_data.entry is not None:
                row_path = str(getattr(row_data.entry, "rel_path", ""))
                if row_path == rename_path:
                    is_rename_row = True

            if is_rename_row:
                self._draw_inline_rename(
                    panel_list_rect.left,
                    panel_list_rect.right,
                    row_bottom,
                    row_top,
                    rename_text,
                    rename_cursor,
                    rename_sel_start,
                    rename_sel_end,
                )
                continue

            is_primary_selected = selected_row_id is not None and id(row_data) == selected_row_id
            is_selected = bool(selected_row_ids and id(row_data) in selected_row_ids) or is_primary_selected

            if row_data.kind == "header":
                label = str(row_data.header or "")
                color = PROJECT_DIM_COLOR
            elif row_data.kind == "action":
                label = format_project_action_label(row_data)
                color = PROJECT_TEXT_COLOR if getattr(row_data, "enabled", True) else PROJECT_DIM_COLOR
            elif row_data.recent is not None:
                label = format_project_recent_label(row_data.recent)
                color = PROJECT_TEXT_COLOR
            else:
                label = format_project_row_label(row_data.entry)
                color = PROJECT_TEXT_COLOR

            row = PanelRow(
                PanelField(
                    label,
                    None,
                    label_color=color,
                    label_font_size=11,
                ),
                height=PROJECT_LINE_HEIGHT,
                padding_x=2.0,
                selected_bg=PROJECT_SELECTED_BG,
            )
            row.set_selected(is_selected)
            rows_panel = EditorPanelBase(
                Rect(
                    x=float(panel_list_rect.left),
                    y=float(row_bottom),
                    width=float(panel_list_rect.right - panel_list_rect.left),
                    height=float(row_top - row_bottom),
                ),
                panel_bg=EDITOR_THEME.transparent,
                panel_border=EDITOR_THEME.transparent,
                item_spacing=0.0,
                inner_padding_x=0.0,
                inner_padding_y=0.0,
            )
            rows_panel.add_row(row)
            rows_panel.draw()
            if has_multi and is_primary_selected:
                _draw_tb_rectangle_outline(
                    panel_list_rect.left,
                    panel_list_rect.right,
                    row_top,
                    row_bottom,
                    PROJECT_RENAME_BORDER,
                    1,
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
        _draw_tb_rectangle_outline(left, right, top, bottom, PROJECT_RENAME_BORDER, 1)

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
                    EDITOR_THEME.tree_selected_bg,
                )

        # Draw cursor (blinking)
        import time
        blink = int(time.time() * 2) % 2 == 0
        if blink:
            cursor_x = left + TEXT_OFFSET + cursor_pos * CHAR_WIDTH
            # Draw cursor line
            _draw_tb_rectangle_outline(
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


def _build_project_explorer_scrolllist(
    *,
    rows: list[Any],
    panel_list_rect: Rect,
    row_height: float,
    start_index: int,
    scroll_y: float,
    selected_row_id: Any,
    format_project_action_label: Any,
    format_project_recent_label: Any,
    format_project_row_label: Any,
) -> ScrollList:
    labels: list[str] = []
    for row in rows:
        if getattr(row, "kind", "") == "header":
            labels.append(str(getattr(row, "header", "") or ""))
            continue
        if getattr(row, "kind", "") == "action":
            labels.append(str(format_project_action_label(row)))
            continue
        recent = getattr(row, "recent", None)
        if recent is not None:
            labels.append(str(format_project_recent_label(recent)))
            continue
        entry = getattr(row, "entry", None)
        labels.append(str(format_project_row_label(entry)) if entry is not None else "")

    selected_index = 0
    if selected_row_id is not None:
        try:
            selected_row_id_int = int(selected_row_id)
        except Exception:
            selected_row_id_int = None
        for idx, row in enumerate(rows):
            if selected_row_id_int is not None and id(row) == selected_row_id_int:
                selected_index = idx
                break

    row_h = max(1, int(row_height))
    local_offset = max(0.0, (float(scroll_y) / float(row_h)) - float(start_index))
    scroll_list = ScrollList(
        items=labels,
        row_height=row_h,
        selected_index=selected_index,
        scroll_offset=local_offset,
    )
    scroll_list.layout(panel_list_rect)
    return scroll_list


def _selected_project_row_from_scrolllist(rows: list[Any], scroll_list: ScrollList) -> Any | None:
    idx = int(getattr(scroll_list, "selected_index", -1))
    if idx < 0 or idx >= len(rows):
        return None
    return rows[idx]
