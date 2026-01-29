"""Find Everything overlay for editor quick launcher."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..text_draw import TextCache, draw_text_cached
from .common import UIElement, draw_panel_bg, _draw_rectangle_filled
from ..editor.find_everything_model import (
    build_find_display_rows,
    build_find_everything_hint_line,
)

if TYPE_CHECKING:  # pragma: no cover
    from ..game import GameWindow


LINE_HEIGHT = 18.0
PANEL_MIN_W = 520.0
PANEL_MAX_W = 760.0
PANEL_MIN_H = 140.0

TEXT_COLOR = (220, 220, 230, 255)
DIM_COLOR = (150, 150, 160, 255)
SELECT_BG = (90, 140, 200, 140)
HEADER_COLOR = (200, 210, 230, 255)


class FindEverythingOverlay(UIElement):
    """Editor-only overlay for the Find Everything launcher."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self._text_cache = TextCache(max_size=256)

    def draw(self) -> None:
        controller = getattr(self.window, "editor_controller", None)
        if controller is None or not getattr(controller, "active", False):
            return
        if not getattr(controller, "_find_everything_open", False):
            return

        results = list(getattr(controller, "_find_everything_cached_results", []) or [])
        query = str(getattr(controller, "_find_everything_query", "") or "")
        selection = int(getattr(controller, "_find_everything_selection_index", 0) or 0)
        counts = getattr(controller, "_find_everything_counts", {"total": 0, "by_group": {}})
        input_source = "keyboard_mouse"
        manager = getattr(self.window, "input", None)
        if manager is None:
            manager = getattr(getattr(self.window, "input_controller", None), "manager", None)
        if manager is not None:
            input_source = str(getattr(manager, "input_source", input_source))
        hint_line = build_find_everything_hint_line(input_source)

        display_rows = build_find_display_rows(results, counts)
        list_rows = [row for row in display_rows if row.kind != "footer"]
        footer_rows = [row for row in display_rows if row.kind == "footer"]

        header_lines = 3
        hint_lines = 1
        total_lines = header_lines + max(len(list_rows), 1) + hint_lines

        height = max(PANEL_MIN_H, 24.0 + LINE_HEIGHT * float(total_lines))
        width = min(PANEL_MAX_W, max(PANEL_MIN_W, float(self.window.width) * 0.7))
        left = (float(self.window.width) - width) / 2.0
        right = left + width
        bottom = (float(self.window.height) - height) / 2.0
        top = bottom + height

        draw_panel_bg(left, right, bottom, top)

        start_x = left + 20.0
        start_y = top - 20.0

        draw_text_cached(
            "FIND EVERYTHING",
            start_x,
            start_y,
            color=HEADER_COLOR,
            font_size=12,
            cache=self._text_cache,
        )
        draw_text_cached(
            f"Search: {query}",
            start_x,
            start_y - LINE_HEIGHT,
            color=TEXT_COLOR,
            font_size=11,
            cache=self._text_cache,
        )
        draw_text_cached(
            "--------------",
            start_x,
            start_y - LINE_HEIGHT * 2,
            color=DIM_COLOR,
            font_size=11,
            cache=self._text_cache,
        )

        row_y = start_y - LINE_HEIGHT * 3
        if not results:
            draw_text_cached(
                "(No matches)",
                start_x,
                row_y,
                color=DIM_COLOR,
                font_size=11,
                cache=self._text_cache,
            )
        else:
            selection = max(0, min(selection, len(results) - 1))
            for row in list_rows:
                row_top = row_y + LINE_HEIGHT * 0.2
                row_bottom = row_y - LINE_HEIGHT * 0.8
                if row.kind == "row" and row.row_index == selection:
                    _draw_rectangle_filled(left + 10.0, right - 10.0, row_bottom, row_top, SELECT_BG)

                color = TEXT_COLOR if row.kind == "row" else HEADER_COLOR
                draw_text_cached(
                    row.text,
                    start_x,
                    row_y,
                    color=color,
                    font_size=11,
                    cache=self._text_cache,
                )
                row_y -= LINE_HEIGHT

        draw_text_cached(
            hint_line,
            start_x,
            bottom + 12.0,
            color=DIM_COLOR,
            font_size=10,
            cache=self._text_cache,
        )

        if footer_rows:
            footer = footer_rows[0].text
            draw_text_cached(
                footer,
                start_x,
                bottom + 26.0,
                color=DIM_COLOR,
                font_size=10,
                cache=self._text_cache,
            )
