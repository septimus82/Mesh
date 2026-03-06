from __future__ import annotations

from typing import TYPE_CHECKING, Any

import engine.optional_arcade as optional_arcade

from ..text_draw import TextCache, draw_text_cached
from .common import UIElement, _draw_lrtb_rectangle_outline, _draw_rectangle_filled, draw_panel_bg
from .widget_overlay_helpers import (
    OverlayFocusModel,
    build_empty_row,
    build_status_row,
    compose_list_rows,
    resolve_preserved_selection_index,
)
from .widgets import Rect, ScrollList, TextInput

if TYPE_CHECKING:  # pragma: no cover
    from ..game import GameWindow


LINE_HEIGHT = 18.0
TEXT_COLOR = (220, 220, 230, 255)
DIM_COLOR = (150, 150, 160, 255)
SELECT_BG = (90, 140, 200, 140)
HEADER_COLOR = (200, 210, 230, 255)
ROW_HEIGHT = int(LINE_HEIGHT)


def _scene_browser_empty_state_text() -> str:
    return build_empty_row("(No scenes)")


def _scene_browser_status_row_text(total_results: int, selection_index: int) -> str:
    return build_status_row(count=total_results, selected_index=selection_index)


def _widgetized_shortcuts_hint_row_text() -> str:
    return "Hints: Tab focus | Ctrl+N/P nav | Ctrl+Enter activate | Enter activates in results"


class SceneBrowserOverlay(UIElement):
    """Editor-only overlay for the scene browser panel."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self._text_cache = TextCache(max_size=96)
        self._text_input = TextInput(
            text="",
            placeholder="Type to filter scenes...",
            focused=True,
            font_size=11,
            height=18.0,
        )
        self._results_scroll = ScrollList(items=[], row_height=ROW_HEIGHT, selected_index=0, scroll_offset=0.0)
        self._rows: list[Any] = []
        self._results_rect: Rect | None = None
        self._focus_model = OverlayFocusModel("input")
        self._focus_target: str = "input"
        self._was_open = False

    def _set_focus(self, focus: str) -> None:
        self._focus_target = self._focus_model.reset(focus)
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
        from ..editor.editor_modal_state_query import is_scene_browser_active

        if controller is None or not getattr(controller, "active", False):
            return False
        if not is_scene_browser_active(controller):
            return False
        dock = getattr(controller, "dock", None)
        snapshot = dock.get_snapshot() if dock is not None and hasattr(dock, "get_snapshot") else dock
        left_dock_tab = getattr(snapshot, "left_tab", "Outliner") or "Outliner"
        return left_dock_tab == "Scene"

    def _set_controller_query(self, controller: object, query: str) -> None:
        rows_getter = getattr(controller, "_scene_browser_rows", None)
        previous_rows: list[Any] = []
        previous_index = int(getattr(controller, "scene_browser_index", 0) or 0)
        if callable(rows_getter):
            previous_rows = list(rows_getter())

        setattr(controller, "scene_browser_query", str(query or ""))
        refresher = getattr(controller, "_refresh_scene_browser_rows", None)
        if callable(refresher):
            refresher()

        if callable(rows_getter):
            new_rows = list(rows_getter())
            resolved_idx, _preserved = resolve_preserved_selection_index(
                previous_rows,
                new_rows,
                previous_index,
                identity_fn=lambda row: str(getattr(row, "scene_id", "") or "") or None,
                clamp_fn=lambda index, _count: int(index),
                fallback_index=previous_index,
            )
            setattr(controller, "scene_browser_index", resolved_idx)

        clamped = getattr(controller, "_scene_browser_clamp_index", None)
        if callable(clamped) and callable(rows_getter):
            clamped(len(list(rows_getter())))

    def _set_controller_selected_index(self, controller: object, selected_index: int) -> None:
        setattr(controller, "scene_browser_index", int(selected_index))
        clamped = getattr(controller, "_scene_browser_clamp_index", None)
        rows_getter = getattr(controller, "_scene_browser_rows", None)
        if callable(clamped) and callable(rows_getter):
            clamped(len(list(rows_getter())))

    def _sync_scroll_selection_from_controller(self, controller: object) -> None:
        rows_getter = getattr(controller, "_scene_browser_rows", None)
        if not callable(rows_getter):
            return
        count = len(list(rows_getter()))
        selected = int(getattr(controller, "scene_browser_index", 0) or 0)
        if count <= 0:
            self._results_scroll.selected_index = -1
            return
        selected = max(0, min(selected, count - 1))
        self._results_scroll.selected_index = selected
        bounds = self._results_rect
        if bounds is not None:
            self._results_scroll.layout(bounds)
            self._results_scroll.ensure_visible(selected)

    def toggle_focus(self) -> bool:
        self._focus_target = self._focus_model.toggle_focus()
        self._text_input.focused = self._focus_target == "input"
        return True

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

    def on_key_enter(self) -> bool:
        controller = self._get_controller()
        if not self._is_visible_for_controller(controller):
            return False
        if self._focus_target != "results":
            return True
        self.activate_selected()
        return True

    def activate_selected(self) -> bool:
        controller = self._get_controller()
        if not self._is_visible_for_controller(controller):
            return False
        opener = getattr(controller, "_scene_browser_open_selected", None)
        if callable(opener):
            return bool(opener())
        return False

    def handle_navigation_key(self, key: int) -> bool:
        controller = self._get_controller()
        if not self._is_visible_for_controller(controller):
            return False
        if self._focus_target != "results":
            return False
        page_up_key = getattr(optional_arcade.arcade.key, "PAGE_UP", None)
        if page_up_key is None:
            page_up_key = getattr(optional_arcade.arcade.key, "PAGEUP", None)
        page_down_key = getattr(optional_arcade.arcade.key, "PAGE_DOWN", None)
        if page_down_key is None:
            page_down_key = getattr(optional_arcade.arcade.key, "PAGEDOWN", None)
        changed = False
        if key == optional_arcade.arcade.key.UP:
            changed = self._results_scroll.on_key_up()
        elif key == optional_arcade.arcade.key.DOWN:
            changed = self._results_scroll.on_key_down()
        elif page_up_key is not None and key == page_up_key:
            changed = self._results_scroll.on_key_page_up()
        elif page_down_key is not None and key == page_down_key:
            changed = self._results_scroll.on_key_page_down()
        elif key == optional_arcade.arcade.key.HOME:
            changed = self._results_scroll.on_key_home()
        elif key == optional_arcade.arcade.key.END:
            changed = self._results_scroll.on_key_end()
        else:
            return False
        if changed:
            self._set_controller_selected_index(controller, int(self._results_scroll.selected_index))
            self._sync_scroll_selection_from_controller(controller)
        return True

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
            return True
        input_rect = self._text_input.last_rect
        input_changed = self._text_input.on_mouse_press(x, y)
        if input_rect is not None and input_rect.contains(float(x), float(y)):
            self._set_focus("input")
            return True
        bounds = self._results_rect
        if bounds is None or not bounds.contains(float(x), float(y)):
            return bool(input_changed)
        clicked = self._results_scroll.on_mouse_press(float(x), float(y))
        if not clicked:
            return bool(input_changed)
        self._set_focus("results")
        self._set_controller_selected_index(controller, int(self._results_scroll.selected_index))
        opener = getattr(controller, "_scene_browser_open_selected", None)
        if callable(opener):
            opener()
        return True

    def draw(self) -> None:
        controller = self._get_controller()
        if not self._is_visible_for_controller(controller):
            self._was_open = False
            self._text_input.focused = False
            self._focus_model.reset("input")
            self._focus_target = "input"
            return
        if not self._was_open:
            self._set_focus("input")
            self._was_open = True

        rows_getter = getattr(controller, "_scene_browser_rows", None)
        layout_getter = getattr(controller, "_scene_browser_layout", None)
        if not callable(rows_getter) or not callable(layout_getter):
            return
        rows = list(rows_getter())
        layout = layout_getter(len(rows))
        if not isinstance(layout, dict):
            return

        query = str(getattr(controller, "scene_browser_query", "") or "")
        self._text_input.text = query
        self._rows = rows
        self._results_scroll.items = [
            f"{str(getattr(row, 'display_name', '') or '')} [{str(getattr(row, 'pack_name', '') or 'root')}]"
            for row in rows
        ]
        self._results_scroll.row_height = int(ROW_HEIGHT)

        draw_panel_bg(layout["left"], layout["right"], layout["bottom"], layout["top"])
        start_x = float(layout["start_x"])
        start_y = float(layout["start_y"])

        draw_text_cached(
            "SCENE BROWSER",
            start_x,
            start_y,
            color=HEADER_COLOR,
            font_size=12,
            cache=self._text_cache,
        )

        input_rect = Rect(
            x=start_x,
            y=(start_y - LINE_HEIGHT) - 8.0,
            width=max(80.0, float(layout["right"] - layout["left"]) - 40.0),
            height=18.0,
        )
        input_layout = self._text_input.layout(input_rect)
        _draw_lrtb_rectangle_outline(
            input_rect.left - 2.0,
            input_rect.right + 2.0,
            input_rect.top + 2.0,
            input_rect.bottom - 2.0,
            (90, 120, 170, 180) if self._text_input.focused else (85, 85, 95, 120),
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
            start_y - (LINE_HEIGHT * 2.0),
            color=DIM_COLOR,
            font_size=11,
            cache=self._text_cache,
        )

        results_top = float(layout["row_start_y"]) + (LINE_HEIGHT * 0.6)
        results_bottom = float(layout["bottom"]) + 12.0
        self._results_rect = Rect(
            x=float(layout["left"]) + 10.0,
            y=results_bottom,
            width=max(0.0, float(layout["right"] - layout["left"]) - 20.0),
            height=max(float(ROW_HEIGHT), results_top - results_bottom),
        )
        composed_rows = compose_list_rows(
            [str(getattr(row, "display_name", "") or "") for row in rows],
            empty_row=_scene_browser_empty_state_text(),
            status_row=_scene_browser_status_row_text(len(rows), int(getattr(controller, "scene_browser_index", 0) or 0)),
            hints_row=_widgetized_shortcuts_hint_row_text(),
            show_status=True,
        )

        selected_index = int(getattr(controller, "scene_browser_index", 0) or 0)
        self._results_scroll.selected_index = selected_index

        if not rows:
            draw_text_cached(
                composed_rows[0] if composed_rows else _scene_browser_empty_state_text(),
                start_x,
                float(layout["row_start_y"]),
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
                row_index = payload.get("row_index")
                rect = payload.get("rect")
                if not isinstance(row_index, int) or not isinstance(rect, Rect):
                    continue
                if row_index < 0 or row_index >= len(rows):
                    continue
                row = rows[row_index]
                if kind == "scroll_row_bg":
                    if bool(payload.get("selected", False)):
                        _draw_rectangle_filled(rect.left, rect.right, rect.bottom, rect.top, SELECT_BG)
                    continue
                if kind == "scroll_row_text":
                    color = optional_arcade.arcade.color.YELLOW if bool(getattr(row, "is_recent", False)) else TEXT_COLOR
                    draw_text_cached(
                        str(payload.get("text", "")),
                        start_x,
                        rect.bottom + 2.0,
                        color=color,
                        font_size=11,
                        cache=self._text_cache,
                    )

        status_row = _scene_browser_status_row_text(len(rows), int(getattr(controller, "scene_browser_index", 0) or 0))
        hints_row = _widgetized_shortcuts_hint_row_text()
        if len(composed_rows) >= 2:
            status_row = composed_rows[-2]
            hints_row = composed_rows[-1]
        elif composed_rows:
            status_row = composed_rows[-1]

        draw_text_cached(status_row, start_x, float(layout["bottom"]) + 12.0, color=DIM_COLOR, font_size=10, cache=self._text_cache)
        draw_text_cached(hints_row, start_x, float(layout["bottom"]) + 2.0, color=DIM_COLOR, font_size=10, cache=self._text_cache)
