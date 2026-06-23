"""Find Everything overlay for editor quick launcher."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import engine.optional_arcade as optional_arcade

from ..text_draw import TextCache, draw_text_cached
from .common import UIElement, _draw_rectangle_filled, _draw_tb_rectangle_outline, draw_panel_bg
from .theme import EDITOR_THEME
from .widget_overlay_helpers import build_empty_row, build_status_row, compose_list_rows
from .widgets import Rect, ScrollList, TextInput

if TYPE_CHECKING:  # pragma: no cover
    from ..game import GameWindow


LINE_HEIGHT = 18.0
PANEL_MIN_W = 520.0
PANEL_MAX_W = 760.0
PANEL_MIN_H = 140.0

TEXT_COLOR = EDITOR_THEME.text_primary
DIM_COLOR = EDITOR_THEME.text_dim
SELECT_BG = EDITOR_THEME.selected_row_bg
HEADER_COLOR = EDITOR_THEME.text_header
RESULT_ROW_HEIGHT = int(LINE_HEIGHT)


def _find_empty_state_text() -> str:
    return build_empty_row("(No matches)")


def _find_status_row_text(total_results: int, selection_index: int) -> str:
    return build_status_row(count=total_results, selected_index=selection_index)


def _find_shortcuts_hint_row_text() -> str:
    return "Hints: Tab focus | Ctrl+N/P nav | Ctrl+Enter activate | Enter activates in results"


class FindEverythingOverlay(UIElement):
    """Editor-only overlay for the Find Everything launcher."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self._text_cache = TextCache(max_size=256)
        self._text_input = TextInput(
            text="",
            placeholder="Type to search...",
            focused=True,
            font_size=11,
            height=18.0,
        )
        self._results_scroll = ScrollList(items=[], row_height=RESULT_ROW_HEIGHT, selected_index=0, scroll_offset=0.0)
        self._result_rows: list[Any] = []
        self._results_rect: Rect | None = None
        self._focus_target: str = "input"
        self._was_open = False

    def _set_focus(self, focus: str) -> None:
        self._focus_target = "results" if focus == "results" else "input"
        self._text_input.focused = self._focus_target == "input"

    def reset_for_open(self) -> None:
        self._was_open = False
        self._set_focus("input")

    def reset_for_close(self) -> None:
        self._was_open = False
        self._set_focus("input")
        self._text_input.focused = False

    def _get_controller(self) -> object | None:
        return getattr(self.window, "editor_controller", None)

    def _is_visible_for_controller(self, controller: object | None) -> bool:
        return bool(
            controller is not None
            and getattr(controller, "active", False)
            and getattr(controller, "_find_everything_open", False)
        )

    def _sync_text_input_query(self, query: str) -> None:
        value = str(query or "")
        if self._text_input.text != value:
            self._text_input.text = value

    def _set_controller_query(self, controller: object, text: str) -> None:
        setter = getattr(controller, "set_find_query", None)
        if callable(setter):
            setter(text)
            return
        setattr(controller, "_find_everything_query", text)

    def _resolve_selected_display_index(self, selected_result_index: int) -> int:
        fallback = 0
        for display_index, row in enumerate(self._result_rows):
            kind = str(getattr(row, "kind", "") or "")
            if kind == "row":
                if fallback == 0:
                    fallback = display_index
                row_index = getattr(row, "row_index", None)
                if isinstance(row_index, int) and row_index == selected_result_index:
                    return display_index
        return fallback

    def _resolve_result_index_from_display(self, display_index: int) -> int | None:
        if display_index < 0 or display_index >= len(self._result_rows):
            return None
        row = self._result_rows[display_index]
        if str(getattr(row, "kind", "") or "") != "row":
            return None
        row_index = getattr(row, "row_index", None)
        if isinstance(row_index, int):
            return int(row_index)
        return None

    def _set_controller_selection_index(self, controller: object, target_index: int) -> None:
        current = int(getattr(controller, "_find_everything_selection_index", 0) or 0)
        mover = getattr(controller, "move_find_selection", None)
        if callable(mover):
            mover(int(target_index) - current)
            return
        setattr(controller, "_find_everything_selection_index", int(target_index))

    def _sync_scroll_selection_from_controller(self, controller: object) -> None:
        selected_result = int(getattr(controller, "_find_everything_selection_index", 0) or 0)
        self._results_scroll.selected_index = int(self._resolve_selected_display_index(selected_result))
        bounds = self._results_rect
        if bounds is not None:
            layout = self._results_scroll.layout(bounds)
            _ = layout
            start = self._results_scroll.visible_start_index
            cap = self._results_scroll.visible_capacity
            idx = int(self._results_scroll.selected_index)
            if cap > 0:
                if idx < start:
                    self._results_scroll.scroll_offset = float(idx)
                    self._results_scroll.layout(bounds)
                elif idx >= (start + cap):
                    self._results_scroll.scroll_offset = float(max(0, idx - cap + 1))
                    self._results_scroll.layout(bounds)

    def append_text(self, text: str) -> bool:
        controller = self._get_controller()
        if not self._is_visible_for_controller(controller):
            return False
        if self._focus_target != "input":
            return False
        if not self._text_input.on_text_input(text):
            return False
        self._set_controller_query(controller, self._text_input.text)
        return True

    def backspace(self) -> bool:
        controller = self._get_controller()
        if not self._is_visible_for_controller(controller):
            return False
        if self._focus_target != "input":
            return False
        if not self._text_input.on_key_backspace():
            return False
        self._set_controller_query(controller, self._text_input.text)
        return True

    def submit(self) -> bool:
        if self._focus_target != "input":
            return False
        return bool(self._text_input.on_key_enter())

    def toggle_focus(self) -> bool:
        self._set_focus("results" if self._focus_target == "input" else "input")
        return True

    def handle_navigation_key(self, key: int) -> bool:
        if key == optional_arcade.arcade.key.UP:
            return self.move_selection(-1)
        if key == optional_arcade.arcade.key.DOWN:
            return self.move_selection(1)
        return False

    def on_key_enter(self) -> bool:
        if self._focus_target == "results":
            self.activate_selected()
            return True
        return True

    def move_selection(self, delta: int) -> bool:
        controller = self._get_controller()
        if not self._is_visible_for_controller(controller):
            return False
        if self._focus_target == "results":
            moved = False
            step = 1 if int(delta) > 0 else -1
            remaining = abs(int(delta))
            while remaining > 0:
                changed = self._results_scroll.on_key_down() if step > 0 else self._results_scroll.on_key_up()
                target_result_index = self._resolve_result_index_from_display(int(self._results_scroll.selected_index))
                if target_result_index is not None:
                    self._set_controller_selection_index(controller, target_result_index)
                    moved = True
                    remaining -= 1
                elif not changed:
                    break
            if moved:
                self._sync_scroll_selection_from_controller(controller)
                return True
            return False
        mover = getattr(controller, "move_find_selection", None)
        if callable(mover):
            mover(int(delta))
            self._sync_scroll_selection_from_controller(controller)
            return True
        return False

    def activate_selected(self) -> bool:
        controller = self._get_controller()
        if not self._is_visible_for_controller(controller):
            return False
        activator = getattr(controller, "activate_find_selection", None)
        if callable(activator):
            return bool(activator())
        return False

    def on_mouse_scroll(self, x: float, y: float, scroll_x: float, scroll_y: float) -> bool:  # noqa: ARG002
        controller = self._get_controller()
        if not self._is_visible_for_controller(controller):
            return False
        bounds = self._results_rect
        if bounds is None or not bounds.contains(float(x), float(y)):
            return False
        return bool(self._results_scroll.on_mouse_wheel(float(scroll_y)))

    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int = 0) -> bool:  # noqa: ARG002
        controller = self._get_controller()
        if not self._is_visible_for_controller(controller):
            return False
        if button != optional_arcade.arcade.MOUSE_BUTTON_LEFT:
            return False
        input_rect = self._text_input.last_rect
        input_changed = self._text_input.on_mouse_press(x, y)
        if input_rect is not None and input_rect.contains(float(x), float(y)):
            self._set_focus("input")
            return True

        results_rect = self._results_rect
        if results_rect is None or not results_rect.contains(float(x), float(y)):
            return bool(input_changed)
        clicked = self._results_scroll.on_mouse_press(float(x), float(y))
        if not clicked:
            return bool(input_changed)
        self._set_focus("results")
        target_result_index = self._resolve_result_index_from_display(int(self._results_scroll.selected_index))
        if target_result_index is not None:
            self._set_controller_selection_index(controller, target_result_index)
            self._sync_scroll_selection_from_controller(controller)
        return True

    def draw(self) -> None:
        from ..editor.find_everything_model import (
            build_find_display_rows,
            build_find_everything_hint_line,
        )

        controller = self._get_controller()
        if not self._is_visible_for_controller(controller):
            self._was_open = False
            self._text_input.focused = False
            self._set_focus("input")
            return

        if not self._was_open:
            self._set_focus("input")
            self._was_open = True

        results = list(getattr(controller, "_find_everything_cached_results", []) or [])
        query = str(getattr(controller, "_find_everything_query", "") or "")
        self._sync_text_input_query(query)
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
        self._result_rows = list(list_rows)
        self._results_scroll.items = [str(getattr(row, "text", "") or "") for row in self._result_rows]
        self._results_scroll.row_height = int(RESULT_ROW_HEIGHT)

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
        input_rect = Rect(
            x=start_x,
            y=(start_y - LINE_HEIGHT) - 8.0,
            width=max(80.0, (right - left) - 40.0),
            height=18.0,
        )
        input_layout = self._text_input.layout(input_rect)
        _draw_tb_rectangle_outline(
            input_rect.left - 2.0,
            input_rect.right + 2.0,
            input_rect.top + 2.0,
            input_rect.bottom - 2.0,
            EDITOR_THEME.field_border_focus if self._text_input.focused else EDITOR_THEME.field_border_idle,
            1.0,
        )
        for instruction in input_layout.instructions:
            if instruction.kind == "text_input_text":
                payload = instruction.payload
                text = str(payload.get("text") or "")
                is_placeholder = bool(payload.get("is_placeholder", False))
                draw_text_cached(
                    f"Search: {text}",
                    start_x,
                    start_y - LINE_HEIGHT,
                    color=DIM_COLOR if is_placeholder else TEXT_COLOR,
                    font_size=11,
                    cache=self._text_cache,
                )
            elif instruction.kind == "text_input_caret":
                draw_text_cached(
                    "|",
                    start_x + 56.0 + (float(len(query)) * 6.0),
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
        results_top = row_y + (LINE_HEIGHT * 0.2)
        results_bottom = bottom + 40.0
        self._results_rect = Rect(
            x=left + 10.0,
            y=results_bottom,
            width=max(0.0, (right - left) - 20.0),
            height=max(float(RESULT_ROW_HEIGHT), results_top - results_bottom),
        )
        composed_rows = compose_list_rows(
            [str(getattr(row, "text", "") or "") for row in self._result_rows],
            empty_row=_find_empty_state_text(),
            status_row=_find_status_row_text(len(results), selection),
            hints_row=_find_shortcuts_hint_row_text(),
            show_status=True,
        )
        self._results_scroll.selected_index = self._resolve_selected_display_index(selection)
        if not results:
            draw_text_cached(
                composed_rows[0] if composed_rows else _find_empty_state_text(),
                start_x,
                row_y,
                color=DIM_COLOR,
                font_size=11,
                cache=self._text_cache,
            )
        else:
            self._sync_scroll_selection_from_controller(controller)
            list_layout = self._results_scroll.layout(self._results_rect)
            for instruction in list_layout.instructions:
                kind = str(instruction.kind or "")
                payload = instruction.payload if isinstance(instruction.payload, dict) else {}
                if kind == "scroll_row_bg":
                    rect = payload.get("rect")
                    row_index = payload.get("row_index")
                    selected_row = bool(payload.get("selected", False))
                    if not isinstance(rect, Rect) or not isinstance(row_index, int):
                        continue
                    if row_index < 0 or row_index >= len(self._result_rows):
                        continue
                    row = self._result_rows[row_index]
                    if selected_row and str(getattr(row, "kind", "") or "") == "row":
                        _draw_rectangle_filled(rect.left, rect.right, rect.bottom, rect.top, SELECT_BG)
                    continue
                if kind == "scroll_row_text":
                    rect = payload.get("rect")
                    row_index = payload.get("row_index")
                    if not isinstance(rect, Rect) or not isinstance(row_index, int):
                        continue
                    if row_index < 0 or row_index >= len(self._result_rows):
                        continue
                    row = self._result_rows[row_index]
                    row_kind = str(getattr(row, "kind", "") or "")
                    color = HEADER_COLOR if row_kind == "header" else TEXT_COLOR
                    draw_text_cached(
                        str(getattr(row, "text", "") or ""),
                        start_x,
                        rect.bottom + 2.0,
                        color=color,
                        font_size=11,
                        cache=self._text_cache,
                    )

        status_row = _find_status_row_text(len(results), selection)
        hints_row = _find_shortcuts_hint_row_text()
        if len(composed_rows) >= 2:
            status_row = composed_rows[-2]
            hints_row = composed_rows[-1]
        elif composed_rows:
            status_row = composed_rows[-1]

        draw_text_cached(status_row, start_x, bottom + 26.0, color=DIM_COLOR, font_size=10, cache=self._text_cache)

        draw_text_cached(
            hints_row,
            start_x,
            bottom + 12.0,
            color=DIM_COLOR,
            font_size=10,
            cache=self._text_cache,
        )

        draw_text_cached(
            hint_line,
            start_x,
            bottom + 2.0,
            color=DIM_COLOR,
            font_size=10,
            cache=self._text_cache,
        )

        if footer_rows:
            footer = footer_rows[0].text
            draw_text_cached(
                footer,
                start_x,
                bottom + 40.0,
                color=DIM_COLOR,
                font_size=10,
                cache=self._text_cache,
            )
