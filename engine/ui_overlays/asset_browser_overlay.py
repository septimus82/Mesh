"""Asset Browser Overlay."""

# ruff: noqa: F401

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import engine.optional_arcade as optional_arcade

from ..text_draw import TextCache, draw_text_cached
from .common import UIElement, _draw_rectangle_filled, _draw_tb_rectangle_outline, draw_panel_bg
from .widget_overlay_helpers import OverlayFocusModel, build_empty_row, build_status_row, compose_list_rows
from .widgets import Rect, ScrollList, TextInput

if TYPE_CHECKING:  # pragma: no cover
    from ..game import GameWindow


def _asset_browser_empty_state_text() -> str:
    return build_empty_row("(No assets)")


def _asset_browser_status_row_text(total_results: int, selection_index: int) -> str:
    return build_status_row(count=total_results, selected_index=selection_index)


def _widgetized_shortcuts_hint_row_text() -> str:
    return "Hints: Tab focus | Ctrl+N/P nav | Ctrl+Enter activate | Enter activates in results"


class AssetBrowserOverlay(UIElement):
    """Editor-only overlay for browsing assets."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self._text_cache = TextCache(max_size=128)
        self._text_input = TextInput(
            text="",
            placeholder="Search assets...",
            focused=True,
            font_size=14,
            height=24.0,
        )
        self._results_scroll = ScrollList(items=[], row_height=24, selected_index=0, scroll_offset=0.0)
        self._rows: list[Any] = []
        self._list_rect: Rect | None = None
        self._focus_model = OverlayFocusModel("input")
        self._focus_target: str = "input"
        self._was_open = False

    def _set_focus(self, focus: str) -> None:
        self._focus_target = self._focus_model.reset(focus)
        self._text_input.focused = self._focus_target == "input"

    def _get_controller(self) -> object | None:
        return getattr(self.window, "editor_controller", None)

    def _is_visible_for_controller(self, controller: object | None) -> bool:
        if controller is None or not getattr(controller, "active", False):
            return False
        if not getattr(controller, "asset_browser_active", False):
            return False
        dock = getattr(controller, "dock", None)
        snapshot = dock.get_snapshot() if dock is not None and hasattr(dock, "get_snapshot") else dock
        right_dock_tab = getattr(snapshot, "right_tab", "Inspector") or "Inspector"
        return right_dock_tab == "Assets"

    def reset_for_open(self) -> None:
        self._was_open = False
        self._set_focus("input")

    def reset_for_close(self) -> None:
        self._was_open = False
        self._set_focus("input")
        self._text_input.focused = False

    def _set_controller_selection_index(self, controller: object, index: int) -> None:
        rows = list(getattr(controller, "_asset_browser_filtered_rows", []) or [])
        if not rows:
            setattr(controller, "asset_browser_selection_index", 0)
            return
        clamped = max(0, min(int(index), len(rows) - 1))
        setattr(controller, "asset_browser_selection_index", clamped)

    def _sync_scroll_selection_from_controller(self, controller: object) -> None:
        rows = self._rows
        selected = int(getattr(controller, "asset_browser_selection_index", 0) or 0)
        if not rows:
            self._results_scroll.selected_index = -1
            return
        selected = max(0, min(selected, len(rows) - 1))
        self._results_scroll.selected_index = selected
        bounds = self._list_rect
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
        setter = getattr(controller, "set_asset_browser_filter", None)
        if callable(setter):
            setter(self._text_input.text)
            return True
        return False

    def backspace(self) -> bool:
        controller = self._get_controller()
        if not self._is_visible_for_controller(controller):
            return False
        if self._focus_target != "input":
            return False
        if not self._text_input.on_key_backspace():
            return False
        setter = getattr(controller, "set_asset_browser_filter", None)
        if callable(setter):
            setter(self._text_input.text)
            return True
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
        home_key = getattr(optional_arcade.arcade.key, "HOME", None)
        end_key = getattr(optional_arcade.arcade.key, "END", None)
        changed = False
        if key == optional_arcade.arcade.key.UP:
            changed = self._results_scroll.on_key_up()
        elif key == optional_arcade.arcade.key.DOWN:
            changed = self._results_scroll.on_key_down()
        elif page_up_key is not None and key == page_up_key:
            changed = self._results_scroll.on_key_page_up()
        elif page_down_key is not None and key == page_down_key:
            changed = self._results_scroll.on_key_page_down()
        elif home_key is not None and key == home_key:
            changed = self._results_scroll.on_key_home()
        elif end_key is not None and key == end_key:
            changed = self._results_scroll.on_key_end()
        else:
            return False
        if changed:
            self._set_controller_selection_index(controller, int(self._results_scroll.selected_index))
            self._sync_scroll_selection_from_controller(controller)
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
        activator = getattr(controller, "_activate_selected_asset", None)
        if callable(activator):
            activator()
            return True
        return False

    def on_mouse_scroll(self, x: float, y: float, scroll_x: float, scroll_y: float) -> bool:  # noqa: ARG002
        controller = self._get_controller()
        if not self._is_visible_for_controller(controller):
            return False
        bounds = self._list_rect
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
        bounds = self._list_rect
        if bounds is None or not bounds.contains(float(x), float(y)):
            return bool(input_changed)
        clicked = self._results_scroll.on_mouse_press(float(x), float(y))
        if not clicked:
            return bool(input_changed)
        self._set_focus("results")
        self._set_controller_selection_index(controller, int(self._results_scroll.selected_index))
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

        from ..editor.editor_dock_query import get_effective_dock_widths
        from ..editor.editor_shell_layout import TAB_HEADER_HEIGHT, compute_editor_shell_layout

        window_w = int(getattr(self.window, "width", 1280) or 1280)
        window_h = int(getattr(self.window, "height", 720) or 720)
        left_w, right_w = get_effective_dock_widths(controller, window_w)
        layout = compute_editor_shell_layout(window_w, window_h, left_w, right_w)
        dock = layout.right_dock

        left = dock.left
        right = dock.right
        top = dock.top
        bottom = dock.bottom

        draw_panel_bg(left, right, bottom, top)

        padding = 8.0
        filter_h = 24.0
        footer_h = 28.0
        content_top = top - TAB_HEADER_HEIGHT - padding
        search_rect_l = left + padding
        search_rect_r = right - padding
        search_rect_t = content_top
        search_rect_b = search_rect_t - filter_h

        search = getattr(controller, "search", None)
        filter_text = search.get_assets_search() if search is not None else ""
        kind_text = getattr(controller, "asset_browser_kind", "All")
        self._text_input.text = str(filter_text or "")
        input_layout = self._text_input.layout(
            Rect(
                x=float(search_rect_l),
                y=float(search_rect_b),
                width=float(search_rect_r - search_rect_l),
                height=float(search_rect_t - search_rect_b),
            )
        )
        draw_text_cached(
            f"Filter: {self._text_input.text or 'Search assets...'}",
            search_rect_l,
            search_rect_b + 6,
            color=(255, 255, 255),
            font_size=11,
            cache=self._text_cache,
        )
        if self._text_input.focused:
            draw_text_cached(
                "|",
                search_rect_l + 46 + (len(str(self._text_input.text)) * 6),
                search_rect_b + 6,
                color=(255, 255, 255),
                font_size=11,
                cache=self._text_cache,
            )
        _ = input_layout
        draw_text_cached(
            f"Kind: {kind_text}",
            search_rect_r,
            search_rect_b + 6,
            color=(100, 200, 255),
            font_size=11,
            anchor_x="right",
            cache=self._text_cache,
        )
        _draw_tb_rectangle_outline(search_rect_l, search_rect_r, search_rect_t, search_rect_b, (255, 255, 255, 50), 1)

        list_top = search_rect_b - padding
        detail_h = 92.0
        detail_top = bottom + footer_h + detail_h
        list_bottom = detail_top + padding

        rows = list(getattr(controller, "_asset_browser_filtered_rows", []) or [])
        self._rows = rows
        self._results_scroll.items = [str(getattr(row, "display_name", "") or "") for row in rows]
        self._results_scroll.row_height = 24
        selected_index = int(getattr(controller, "asset_browser_selection_index", 0) or 0)
        self._results_scroll.selected_index = selected_index

        self._list_rect = Rect(
            x=float(search_rect_l),
            y=float(list_bottom),
            width=float(search_rect_r - search_rect_l),
            height=max(0.0, float(list_top - list_bottom)),
        )

        self._sync_scroll_selection_from_controller(controller)
        list_layout = self._results_scroll.layout(self._list_rect)
        composed_rows = compose_list_rows(
            [str(getattr(row, "display_name", "") or "") for row in rows],
            empty_row=_asset_browser_empty_state_text(),
            status_row=_asset_browser_status_row_text(len(rows), selected_index),
            hints_row=_widgetized_shortcuts_hint_row_text(),
            show_status=True,
        )

        self._draw_asset_browser_row_list(list_layout.instructions, rows)

        if not rows:
            draw_text_cached(
                composed_rows[0] if composed_rows else _asset_browser_empty_state_text(),
                search_rect_l,
                list_top - 18,
                color=(170, 170, 180),
                font_size=12,
                cache=self._text_cache,
            )

        sel_idx = int(getattr(controller, "asset_browser_selection_index", 0) or 0)
        if 0 <= sel_idx < len(rows):
            sel_row = rows[sel_idx]
            detail_x = search_rect_l
            detail_y = detail_top - 16
            draw_text_cached("DETAILS", detail_x, detail_y, color=(255, 200, 100), font_size=11, bold=True, cache=self._text_cache)
            detail_y -= 18
            draw_text_cached(f"Name: {sel_row.display_name}", detail_x, detail_y, color=(255, 255, 255), font_size=10, cache=self._text_cache)
            detail_y -= 16
            draw_text_cached(f"Kind: {sel_row.kind}", detail_x, detail_y, color=(255, 255, 255), font_size=10, cache=self._text_cache)
            detail_y -= 16
            draw_text_cached(f"Path: {sel_row.rel_path}", detail_x, detail_y, color=(100, 255, 100), font_size=10, cache=self._text_cache)
        else:
            if not rows and str(filter_text or ""):
                draw_text_cached(
                    "No matches found.",
                    search_rect_l,
                    detail_top - 16,
                    color=(255, 100, 100),
                    font_size=12,
                    cache=self._text_cache,
                )

        status_row = _asset_browser_status_row_text(len(rows), sel_idx)
        hints_row = _widgetized_shortcuts_hint_row_text()
        if len(composed_rows) >= 2:
            status_row = composed_rows[-2]
            hints_row = composed_rows[-1]
        elif composed_rows:
            status_row = composed_rows[-1]

        draw_text_cached(status_row, search_rect_l, bottom + 16, color=(170, 170, 180), font_size=10, cache=self._text_cache)
        draw_text_cached(hints_row, search_rect_l, bottom + 4, color=(170, 170, 180), font_size=10, cache=self._text_cache)

    def _draw_asset_browser_row_list(self, instructions: list[Any], rows: list[Any]) -> None:
        bounds = self._list_rect
        if bounds is None or not rows:
            return

        # Asset rows keep ScrollList's geometry/selection model; this helper
        # only migrates the visible row render composition.
        from ..editor.widgets.panel_primitives import EditorPanelBase, PanelField, PanelRow

        rows_panel = EditorPanelBase(
            Rect(
                x=float(bounds.left),
                y=float(bounds.bottom),
                width=float(bounds.width),
                height=float(bounds.height),
            ),
            panel_bg=(0, 0, 0, 0),
            panel_border=(0, 0, 0, 0),
            item_spacing=0.0,
            inner_padding_x=0.0,
            inner_padding_y=0.0,
        )
        selected_row_indices: set[int] = set()
        for instruction in instructions:
            kind = str(getattr(instruction, "kind", "") or "")
            if kind != "scroll_row_bg":
                continue
            payload = instruction.payload if isinstance(instruction.payload, dict) else {}
            row_index = payload.get("row_index")
            rect = payload.get("rect")
            if not isinstance(row_index, int) or not isinstance(rect, Rect):
                continue
            if row_index < 0 or row_index >= len(rows):
                continue
            if bool(payload.get("selected", False)):
                selected_row_indices.add(row_index)

        for instruction in instructions:
            kind = str(getattr(instruction, "kind", "") or "")
            if kind != "scroll_row_text":
                continue
            payload = instruction.payload if isinstance(instruction.payload, dict) else {}
            row_index = payload.get("row_index")
            rect = payload.get("rect")
            if not isinstance(row_index, int) or not isinstance(rect, Rect):
                continue
            if row_index < 0 or row_index >= len(rows):
                continue
            row_data = rows[row_index]
            is_selected = row_index in selected_row_indices
            row = PanelRow(
                PanelField(
                    str(getattr(row_data, "display_name", "")),
                    str(getattr(row_data, "kind", "")),
                    label_color=(255, 255, 255) if is_selected else (180, 180, 180),
                    value_color=(100, 100, 100),
                    label_font_size=12,
                    value_font_size=10,
                ),
                height=24.0,
                padding_x=5.0,
                selected_bg=(255, 255, 255, 40),
            )
            row.set_selected(is_selected)
            rows_panel.add_row(row)
        rows_panel.draw()
