"""Keybinds UI overlay."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import engine.optional_arcade as optional_arcade

from ..text_draw import TextCache
from ..ui_text_cache import UiTextCache, draw_text
from .common import (
    UIElement,
    _draw_lrtb_rectangle_filled,
    _draw_lrtb_rectangle_outline,
    _draw_rectangle_outline,
)
from .keybinds_provider import get_keybinds_ui_data
from .widget_overlay_helpers import OverlayFocusModel, build_empty_row, build_status_row, compose_list_rows
from .widgets import Rect, ScrollList, TextInput


_SWALLOW_ONCE_TAGS: set[str] = set()

def _log_swallow(tag: str, context: str, *, once: bool = True) -> None:
    if once and tag in _SWALLOW_ONCE_TAGS:
        return
    if once:
        _SWALLOW_ONCE_TAGS.add(tag)
    from engine.logging_tools import get_logger

    get_logger(__name__).debug("SWALLOW[%s] %s", tag, context, exc_info=True)

if TYPE_CHECKING:  # pragma: no cover
    from ..game import GameWindow


def _keybinds_empty_state_text() -> str:
    return build_empty_row("(No keybindings)")


def _keybinds_status_row_text(total_results: int, selected_index: int) -> str:
    return build_status_row(count=total_results, selected_index=selected_index)


def _widgetized_shortcuts_hint_row_text() -> str:
    return "Hints: Tab focus | Ctrl+N/P nav | Ctrl+Enter activate | Enter activates in results"


class KeybindsOverlay(UIElement):
    """Renders the Keybinds UI modal."""

    def __init__(self, window: "GameWindow", visible: bool = False) -> None:
        super().__init__(window)
        self.visible = visible
        self._ui_cache = UiTextCache(getattr(window, "text_cache", TextCache()))
        self._text_input = TextInput(
            text="",
            placeholder="Search keybindings...",
            focused=True,
            font_size=12,
            height=22.0,
        )
        self._results_scroll = ScrollList(items=[], row_height=24, selected_index=0, scroll_offset=0.0)
        self._focus_model = OverlayFocusModel("input")
        self._focus_target: str = "input"
        self._was_open = False
        self._rows: list[Any] = []
        self._list_rect: Rect | None = None

    def _get_keybinds_controller(self) -> Any | None:
        editor = getattr(self.window, "editor_controller", None)
        if editor is None:
            return None
        return getattr(editor, "keybinds", None)

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

    def _set_controller_selected_index(self, controller: Any, index: int) -> None:
        setter = getattr(controller, "set_selected_index", None)
        if callable(setter):
            setter(int(index))
            return
        state = getattr(controller, "state", None)
        rows = list(getattr(controller, "visible_rows", ()) or ())
        if state is None:
            return
        count = len(rows)
        if count <= 0:
            target = -1
        else:
            target = max(0, min(int(index), count - 1))
        try:
            from dataclasses import replace  # noqa: PLC0415

            controller.state = replace(state, selected_index=target)
        except Exception:
            _log_swallow("KEYB-001", "engine/ui_overlays/keybinds_overlay.py pass-only blanket swallow")
            pass

    def _sync_scroll_selection_from_controller(self, controller: Any) -> None:
        state = getattr(controller, "state", None)
        rows = self._rows
        selected = int(getattr(state, "selected_index", 0) or 0)
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
        controller = self._get_keybinds_controller()
        if controller is None:
            return False
        if self._focus_target != "input":
            return False
        if not self._text_input.on_text_input(text):
            return False
        setter = getattr(controller, "set_query", None)
        if callable(setter):
            setter(self._text_input.text)
            return True
        return False

    def backspace(self) -> bool:
        controller = self._get_keybinds_controller()
        if controller is None:
            return False
        if self._focus_target != "input":
            return False
        if not self._text_input.on_key_backspace():
            return False
        setter = getattr(controller, "set_query", None)
        if callable(setter):
            setter(self._text_input.text)
            return True
        return False

    def handle_navigation_key(self, key: int) -> bool:
        controller = self._get_keybinds_controller()
        if controller is None:
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
            self._set_controller_selected_index(controller, int(self._results_scroll.selected_index))
            self._sync_scroll_selection_from_controller(controller)
        return True

    def on_key_enter(self) -> bool:
        controller = self._get_keybinds_controller()
        if controller is None:
            return False
        if self._focus_target != "results":
            return True
        self.activate_selected()
        return True

    def activate_selected(self) -> bool:
        controller = self._get_keybinds_controller()
        if controller is None:
            return False
        starter = getattr(controller, "start_recording_selected", None)
        if callable(starter):
            starter()
            return True
        return False

    def on_mouse_scroll(self, x: float, y: float, scroll_x: float, scroll_y: float) -> bool:  # noqa: ARG002
        bounds = self._list_rect
        if bounds is None:
            return False
        if not bounds.contains(float(x), float(y)):
            return False
        return bool(self._results_scroll.on_mouse_wheel(float(scroll_y)))

    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int = 0) -> bool:  # noqa: ARG002
        if button != optional_arcade.arcade.MOUSE_BUTTON_LEFT:
            return False
        controller = self._get_keybinds_controller()
        if controller is None:
            return False
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
        self._set_controller_selected_index(controller, int(self._results_scroll.selected_index))
        return True

    def draw(self) -> None:
        if not self.visible:
            self._was_open = False
            return

        editor = getattr(self.window, "editor_controller", None)
        if editor is None:
            return
        controller = getattr(editor, "keybinds", None)
        if controller is None:
            return

        if not self._was_open:
            self._set_focus("input")
            self._was_open = True

        KEYBINDS_PALETTE_WIDTH = 800.0
        KEYBINDS_PALETTE_HEIGHT = 600.0
        PANEL_PAD = 14.0
        ROW_HEIGHT = 24
        HEADER_HEIGHT = 50.0
        FOOTER_HEIGHT = 30.0

        win_w, win_h = float(self.window.width), float(self.window.height)
        cx, cy = win_w / 2.0, win_h / 2.0
        left = cx - (KEYBINDS_PALETTE_WIDTH / 2.0)
        right = cx + (KEYBINDS_PALETTE_WIDTH / 2.0)
        top = cy + (KEYBINDS_PALETTE_HEIGHT / 2.0)
        bottom = cy - (KEYBINDS_PALETTE_HEIGHT / 2.0)

        _draw_lrtb_rectangle_filled(left + 2.0, right + 2.0, top - 2.0, bottom - 2.0, (0, 0, 0, 120))
        _draw_lrtb_rectangle_filled(left, right, top, bottom, optional_arcade.arcade.color.BLACK + (245,))
        _draw_rectangle_outline(left, right, top, bottom, optional_arcade.arcade.color.GRAY, 2)

        LIST_AREA_HEIGHT = KEYBINDS_PALETTE_HEIGHT - HEADER_HEIGHT - FOOTER_HEIGHT
        DETAIL_WIDTH = 250.0
        LIST_WIDTH = KEYBINDS_PALETTE_WIDTH - DETAIL_WIDTH

        data = get_keybinds_ui_data(
            controller,
            viewport_height=int(LIST_AREA_HEIGHT),
            row_height=ROW_HEIGHT,
            current_scroll_y=float(self._results_scroll.scroll_offset * ROW_HEIGHT),
        )

        rows_all = list(getattr(controller, "visible_rows", ()) or ())
        self._rows = rows_all
        self._results_scroll.items = [str(getattr(row, "title", "") or "") for row in rows_all]
        self._results_scroll.row_height = int(ROW_HEIGHT)

        query = str(data.get("query", "") or "")
        if self._text_input.text != query:
            self._text_input.text = query

        search_box_top = top - PANEL_PAD
        search_box_bottom = top - PANEL_PAD - 30.0
        search_box_left = left + PANEL_PAD
        search_box_right = right - PANEL_PAD

        input_rect = Rect(
            x=float(search_box_left),
            y=float(search_box_bottom),
            width=float(search_box_right - search_box_left),
            height=float(search_box_top - search_box_bottom),
        )
        input_layout = self._text_input.layout(input_rect)
        _draw_lrtb_rectangle_filled(
            search_box_left,
            search_box_right,
            search_box_top,
            search_box_bottom,
            optional_arcade.arcade.color.DARK_SLATE_GRAY,
        )

        if data.get("recording"):
            pending_conflicts = data.get("pending_conflicts", ())
            banner_color = optional_arcade.arcade.color.RED if pending_conflicts else optional_arcade.arcade.color.DARK_RED
            _draw_lrtb_rectangle_filled(search_box_left, search_box_right, search_box_top, search_box_bottom, banner_color)
            _draw_lrtb_rectangle_outline(
                search_box_left,
                search_box_right,
                search_box_top,
                search_box_bottom,
                optional_arcade.arcade.color.BLACK,
                1,
            )
            rec_target = data.get("recording_target")
            pending_sc = data.get("pending_record_shortcut")
            rec_text = "Recording..."
            if rec_target:
                rec_text = f"Recording for {rec_target[1]}..."
            if pending_sc:
                rec_text += f" Input: {pending_sc}"
            if pending_conflicts:
                c_names = ", ".join([c[1] for c in pending_conflicts])
                rec_text += f" !! CONFLICTS: {c_names} !!"
            draw_text(
                self._ui_cache,
                text=rec_text,
                x=search_box_left + 10.0,
                y=search_box_bottom + 8.0,
                color=optional_arcade.arcade.color.WHITE,
                font_size=12,
                bold=True,
            )
        else:
            for instruction in input_layout.instructions:
                if instruction.kind == "text_input_text":
                    payload = instruction.payload
                    text = str(payload.get("text") or "")
                    is_placeholder = bool(payload.get("is_placeholder", False))
                    draw_text(
                        self._ui_cache,
                        text=text if text else "Search keybindings...",
                        x=search_box_left + 10.0,
                        y=search_box_bottom + 8.0,
                        color=optional_arcade.arcade.color.GRAY if is_placeholder else optional_arcade.arcade.color.WHITE,
                        font_size=12,
                    )
                elif instruction.kind == "text_input_caret":
                    draw_text(
                        self._ui_cache,
                        text="|",
                        x=search_box_left + 10.0 + (float(len(query)) * 7.0),
                        y=search_box_bottom + 8.0,
                        color=optional_arcade.arcade.color.WHITE,
                        font_size=12,
                    )

        list_top = search_box_bottom - 10.0
        list_bottom = bottom + FOOTER_HEIGHT
        list_left = left + PANEL_PAD
        list_right = left + LIST_WIDTH

        self._list_rect = Rect(
            x=float(list_left),
            y=float(list_bottom),
            width=float(list_right - list_left),
            height=float(list_top - list_bottom),
        )

        selected_index = int(data.get("selected_index", 0) or 0)
        self._results_scroll.selected_index = selected_index
        self._sync_scroll_selection_from_controller(controller)
        list_layout = self._results_scroll.layout(self._list_rect)

        scrollbar_w = 4.0
        scrollbar_gap = 6.0
        shortcut_right = list_right - (scrollbar_w + scrollbar_gap)
        label_left = list_left + 8.0
        label_gutter = 8.0
        approx_char_w = max(1.0, 10 * 0.6)

        for instruction in list_layout.instructions:
            kind = str(instruction.kind or "")
            payload = instruction.payload if isinstance(instruction.payload, dict) else {}
            row_index = payload.get("row_index")
            rect = payload.get("rect")
            if not isinstance(row_index, int) or not isinstance(rect, Rect):
                continue
            if row_index < 0 or row_index >= len(rows_all):
                continue
            row = rows_all[row_index]

            if kind == "scroll_row_bg":
                if bool(payload.get("selected", False)):
                    bg_color = optional_arcade.arcade.color.DARK_BLUE
                    if bool(getattr(row, "conflict_ids", ())):
                        bg_color = optional_arcade.arcade.color.DARK_RED
                    elif bool(getattr(row, "has_override", False)):
                        bg_color = optional_arcade.arcade.color.TEAL
                    _draw_lrtb_rectangle_filled(list_left, list_right, rect.top, rect.bottom, bg_color)
                continue

            if kind != "scroll_row_text":
                continue
            title = str(getattr(row, "title", "") or "")
            shortcut_text = str(getattr(row, "shortcut_effective", "") or "")
            max_label_w = max(0.0, (shortcut_right - label_gutter) - label_left)
            max_label_chars = int(max_label_w / approx_char_w) if max_label_w > 0 else 0
            if max_label_chars > 0 and len(title) > max_label_chars:
                if max_label_chars >= 3:
                    title = title[: max(0, max_label_chars - 3)] + "..."
                else:
                    title = title[:max_label_chars]

            text_color = optional_arcade.arcade.color.WHITE
            if bool(getattr(row, "conflict_ids", ())):
                text_color = optional_arcade.arcade.color.RED
            elif bool(getattr(row, "has_override", False)):
                text_color = (
                    optional_arcade.arcade.color.CYAN[0],
                    optional_arcade.arcade.color.CYAN[1],
                    optional_arcade.arcade.color.CYAN[2],
                    200,
                )

            draw_text(
                self._ui_cache,
                text=title,
                x=label_left,
                y=rect.bottom + 6.0,
                color=text_color,
                font_size=10,
            )
            draw_text(
                self._ui_cache,
                text=shortcut_text,
                x=shortcut_right,
                y=rect.bottom + 6.0,
                color=text_color,
                font_size=10,
                align="right",
            )
            if bool(getattr(row, "conflict_ids", ())):
                draw_text(
                    self._ui_cache,
                    text="!",
                    x=list_right - 2.0,
                    y=rect.bottom + 6.0,
                    color=optional_arcade.arcade.color.RED,
                    font_size=10,
                    anchor_x="right",
                    anchor_y="baseline",
                )

        total_rows = len(rows_all)
        composed_rows = compose_list_rows(
            [str(getattr(row, "title", "") or "") for row in rows_all],
            empty_row=_keybinds_empty_state_text(),
            status_row=_keybinds_status_row_text(total_rows, selected_index),
            hints_row=_widgetized_shortcuts_hint_row_text(),
            show_status=True,
        )
        if total_rows <= 0:
            draw_text(
                self._ui_cache,
                text=composed_rows[0] if composed_rows else _keybinds_empty_state_text(),
                x=label_left,
                y=list_top - 24.0,
                color=optional_arcade.arcade.color.GRAY,
                font_size=10,
            )

        visible_count = self._results_scroll.visible_capacity
        start_index = int(self._results_scroll.scroll_offset)
        viewport_h = list_top - list_bottom
        if total_rows > 0 and visible_count > 0 and total_rows > visible_count and viewport_h > 0:
            track_left = list_right - scrollbar_w
            track_right = list_right - 1.0
            track_top = list_top
            track_bottom = list_bottom
            _draw_lrtb_rectangle_filled(
                track_left,
                track_right,
                track_top,
                track_bottom,
                optional_arcade.arcade.color.DARK_SLATE_GRAY,
            )
            ratio = max(0.0, min(1.0, start_index / max(1, (total_rows - visible_count))))
            thumb_h = max(10.0, viewport_h * (visible_count / total_rows))
            usable_h = max(1.0, viewport_h - thumb_h)
            thumb_top = track_top - (ratio * usable_h)
            thumb_bottom = thumb_top - thumb_h
            _draw_lrtb_rectangle_filled(
                track_left,
                track_right,
                thumb_top,
                thumb_bottom,
                optional_arcade.arcade.color.GRAY,
            )

        detail_left = list_right + 10.0
        detail_right = right - PANEL_PAD
        detail_top = list_top
        _draw_lrtb_rectangle_outline(list_right, list_right, detail_top, list_bottom, optional_arcade.arcade.color.GRAY, 1)

        selected_item = data.get("selected_item")
        if isinstance(selected_item, dict):
            dy = detail_top - 20.0
            line_h = 18.0
            draw_text(
                self._ui_cache,
                text=str(selected_item.get("title", "")),
                x=detail_left,
                y=dy,
                color=optional_arcade.arcade.color.WHITE,
                font_size=12,
                bold=True,
                width=detail_right - detail_left - 20.0,
                multiline=True,
            )
            dy -= 40.0
            draw_text(self._ui_cache, text="Action ID:", x=detail_left, y=dy, color=optional_arcade.arcade.color.GRAY, font_size=10)
            draw_text(
                self._ui_cache,
                text=str(selected_item.get("action_id", "")),
                x=detail_left + 60.0,
                y=dy,
                color=optional_arcade.arcade.color.LIGHT_GRAY,
                font_size=10,
            )
            dy -= line_h
            draw_text(self._ui_cache, text="Scope:", x=detail_left, y=dy, color=optional_arcade.arcade.color.GRAY, font_size=10)
            draw_text(
                self._ui_cache,
                text=str(selected_item.get("scope", "")),
                x=detail_left + 60.0,
                y=dy,
                color=optional_arcade.arcade.color.LIGHT_GRAY,
                font_size=10,
            )
            dy -= line_h * 2.0
            draw_text(self._ui_cache, text="Effective:", x=detail_left, y=dy, color=optional_arcade.arcade.color.WHITE, font_size=10)
            draw_text(
                self._ui_cache,
                text=str(selected_item.get("effective", "") or "(None)"),
                x=detail_left + 60.0,
                y=dy,
                color=optional_arcade.arcade.color.YELLOW,
                font_size=10,
            )
            dy -= line_h
            draw_text(self._ui_cache, text="Default:", x=detail_left, y=dy, color=optional_arcade.arcade.color.GRAY, font_size=10)
            draw_text(
                self._ui_cache,
                text=str(selected_item.get("default", "") or "(None)"),
                x=detail_left + 60.0,
                y=dy,
                color=optional_arcade.arcade.color.GRAY,
                font_size=10,
            )
            dy -= line_h * 2.0
            conflicts = selected_item.get("conflicts", ())
            if conflicts:
                draw_text(
                    self._ui_cache,
                    text="Conflicts:",
                    x=detail_left,
                    y=dy,
                    color=optional_arcade.arcade.color.RED,
                    font_size=10,
                    bold=True,
                )
                dy -= line_h
                for conflict_id in conflicts:
                    draw_text(
                        self._ui_cache,
                        text=str(conflict_id),
                        x=detail_left + 10.0,
                        y=dy,
                        color=optional_arcade.arcade.color.RED,
                        font_size=9,
                    )
                    dy -= line_h

        hint_text = str(data.get("hint_text", "") or "")
        if data.get("recording"):
            hint_text = "Press a shortcut... Esc: Cancel"
        draw_text(
            self._ui_cache,
            text=hint_text,
            x=left + PANEL_PAD,
            y=bottom + 8.0,
            color=optional_arcade.arcade.color.GRAY,
            font_size=10,
        )
        if len(composed_rows) >= 2:
            draw_text(
                self._ui_cache,
                text=composed_rows[-1],
                x=left + PANEL_PAD,
                y=bottom + 20.0,
                color=optional_arcade.arcade.color.GRAY,
                font_size=10,
            )

        scope_f = str(data.get("scope_filter", "all") or "all")
        conf_f = bool(data.get("show_conflicts_only", False))
        filter_text = f"Scope: {scope_f.upper()}"
        if conf_f:
            filter_text += " | CONFLICTS ONLY"
        draw_text(
            self._ui_cache,
            text=filter_text,
            x=right - PANEL_PAD,
            y=bottom + 8.0,
            color=optional_arcade.arcade.color.YELLOW if conf_f else optional_arcade.arcade.color.LIGHT_GRAY,
            font_size=10,
            align="right",
        )

        status_text = _keybinds_status_row_text(total_rows, selected_index)
        if len(composed_rows) >= 2:
            status_text = composed_rows[-2]
        elif composed_rows:
            status_text = composed_rows[-1]
        draw_text(
            self._ui_cache,
            text=status_text,
            x=list_right - 6.0,
            y=bottom + 8.0,
            color=optional_arcade.arcade.color.LIGHT_GRAY,
            font_size=10,
            align="right",
        )
