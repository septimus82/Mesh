"""AI Chat overlay for the editor right dock."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import engine.optional_arcade as optional_arcade

from ..text_draw import TextCache, draw_text_cached
from .common import UIElement, _draw_tb_rectangle_filled, _draw_tb_rectangle_outline
from .theme import EDITOR_THEME

if TYPE_CHECKING:  # pragma: no cover
    from ..game import GameWindow


PADDING = 8.0
LINE_H = 18.0
INPUT_H = 28.0
BUTTON_W = 58.0
BUTTON_H = 22.0


class AIChatOverlay(UIElement):
    """Editor-only overlay for the native Claude chat shell."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self._text_cache = TextCache(max_size=256)
        self._input_rect: tuple[float, float, float, float] | None = None
        self._transcript_rect: tuple[float, float, float, float] | None = None
        self._transcript_lines: list[dict[str, Any]] = []
        self._scroll_offset_lines = 0
        self._button_rects: dict[str, tuple[float, float, float, float]] = {}

    def draw(self) -> None:
        from ..editor.editor_dock_query import get_effective_dock_widths
        from ..editor.editor_shell_layout import TAB_HEADER_HEIGHT, compute_editor_shell_layout

        controller = getattr(self.window, "editor_controller", None)
        if controller is None or not getattr(controller, "active", False):
            return
        if not self._is_active_tab(controller):
            self._input_rect = None
            self._transcript_rect = None
            self._transcript_lines = []
            self._button_rects.clear()
            return

        window_w = int(getattr(self.window, "width", 1280) or 1280)
        window_h = int(getattr(self.window, "height", 720) or 720)
        left_w, right_w = get_effective_dock_widths(controller, window_w)
        dock = compute_editor_shell_layout(window_w, window_h, left_w, right_w).right_dock
        chat = getattr(controller, "chat", None)

        _draw_tb_rectangle_filled(dock.left, dock.right, dock.top, dock.bottom, EDITOR_THEME.panel_strong_bg)
        _draw_tb_rectangle_outline(dock.left, dock.right, dock.top, dock.bottom, EDITOR_THEME.panel_strong_border, 1)

        content_top = dock.top - TAB_HEADER_HEIGHT - PADDING
        draw_text_cached(
            "AI Chat",
            dock.left + PADDING,
            content_top - LINE_H + 2,
            color=EDITOR_THEME.header_muted,
            font_size=11,
            cache=self._text_cache,
        )

        input_bottom = dock.bottom + PADDING
        input_right = dock.right - PADDING - (BUTTON_W * 2) - 12
        self._input_rect = (dock.left + PADDING, input_bottom, max(1.0, input_right - dock.left - PADDING), INPUT_H)
        send_rect = (input_right + 4, input_bottom + 3, BUTTON_W, BUTTON_H)
        cancel_rect = (send_rect[0] + BUTTON_W + 4, input_bottom + 3, BUTTON_W, BUTTON_H)
        self._button_rects = {"send": send_rect, "cancel": cancel_rect}

        transcript_bottom = input_bottom + INPUT_H + PADDING
        transcript_top = content_top - LINE_H - PADDING
        self._transcript_rect = (
            dock.left + PADDING,
            transcript_bottom,
            max(1.0, dock.right - dock.left - (PADDING * 2)),
            max(1.0, transcript_top - transcript_bottom),
        )
        self._draw_transcript(chat, dock.left + PADDING, transcript_bottom, dock.right - PADDING, transcript_top)
        self._draw_input(chat)
        self._draw_button(send_rect, "Send", EDITOR_THEME.action_text if not bool(getattr(chat, "is_running", False)) else EDITOR_THEME.text_dim)
        self._draw_button(cancel_rect, "Cancel", EDITOR_THEME.warning_text)

    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int = 0) -> bool:  # noqa: ARG002
        if int(button) != int(optional_arcade.arcade.MOUSE_BUTTON_LEFT):
            return False
        controller = getattr(self.window, "editor_controller", None)
        chat = getattr(controller, "chat", None) if controller is not None else None
        if chat is None:
            return False
        if self._input_rect is not None and _contains(self._input_rect, float(x), float(y)):
            chat.input_focused = True
            return True
        for action, rect in list(self._button_rects.items()):
            if not _contains(rect, float(x), float(y)):
                continue
            chat.input_focused = True
            if action == "send":
                if bool(getattr(chat, "is_running", False)):
                    return True
                submit = getattr(chat, "submit_current_input", None)
                if callable(submit):
                    submit()
                return True
            if action == "cancel":
                cancel = getattr(chat, "cancel", None)
                if callable(cancel):
                    cancel()
                return True
        chat.input_focused = False
        return True

    def on_mouse_scroll(self, x: float, y: float, scroll_x: float, scroll_y: float) -> bool:  # noqa: ARG002
        controller = getattr(self.window, "editor_controller", None)
        if controller is None or not self._is_active_tab(controller):
            return False
        rect = self._transcript_rect
        if rect is None or not _contains(rect, float(x), float(y)):
            return False
        capacity = self._visible_line_capacity(rect)
        max_offset = max(0, len(self._transcript_lines) - capacity)
        previous = self._scroll_offset_lines
        self._scroll_offset_lines = max(0, min(max_offset, self._scroll_offset_lines + int(scroll_y)))
        return previous != self._scroll_offset_lines or max_offset > 0

    def on_text(self, text: str) -> bool:
        controller = getattr(self.window, "editor_controller", None)
        chat = getattr(controller, "chat", None) if controller is not None else None
        append = getattr(chat, "append_input_text", None) if chat is not None else None
        return bool(callable(append) and append(text))

    def handle_key(self, key: int, modifiers: int) -> bool:  # noqa: ARG002
        controller = getattr(self.window, "editor_controller", None)
        chat = getattr(controller, "chat", None) if controller is not None else None
        if chat is None or not bool(getattr(chat, "input_focused", False)):
            return False
        if key == optional_arcade.arcade.key.BACKSPACE:
            return bool(chat.backspace_input())
        if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
            if not bool(getattr(chat, "is_running", False)):
                chat.submit_current_input()
            return True
        if key == optional_arcade.arcade.key.ESCAPE:
            chat.input_focused = False
            return True
        return False

    def _draw_transcript(self, chat: Any, left: float, bottom: float, right: float, top: float) -> None:
        messages = list(getattr(chat, "visible_messages", []) if chat is not None else [])
        approx_char_w = max(1.0, 10 * 0.6)
        max_chars = int(max(1.0, (right - left) / approx_char_w))
        self._transcript_lines = build_transcript_lines(messages, max_chars)
        capacity = self._visible_line_capacity((left, bottom, right - left, max(1.0, top - bottom)))
        max_offset = max(0, len(self._transcript_lines) - capacity)
        self._scroll_offset_lines = max(0, min(max_offset, self._scroll_offset_lines))
        start = max(0, len(self._transcript_lines) - capacity - self._scroll_offset_lines)
        visible = self._transcript_lines[start : start + capacity]
        y = top - LINE_H
        for line in visible:
            role = str(line.get("role", "system"))
            color = EDITOR_THEME.text_primary
            if role == "user":
                color = EDITOR_THEME.action_text
            if line.get("status") == "error":
                color = EDITOR_THEME.warning_text
            draw_text_cached(
                str(line.get("text", "")),
                left,
                y,
                color=color,
                font_size=10,
                cache=self._text_cache,
            )
            y -= LINE_H

    def _visible_line_capacity(self, rect: tuple[float, float, float, float]) -> int:
        _left, _bottom, _width, height = rect
        return max(1, int(float(height) // LINE_H))

    def _draw_input(self, chat: Any) -> None:
        if self._input_rect is None:
            return
        left, bottom, width, height = self._input_rect
        focused = bool(getattr(chat, "input_focused", False)) if chat is not None else False
        _draw_tb_rectangle_filled(left, left + width, bottom + height, bottom, EDITOR_THEME.input_bg_focused if focused else EDITOR_THEME.input_bg)
        _draw_tb_rectangle_outline(left, left + width, bottom + height, bottom, EDITOR_THEME.input_border_focused if focused else EDITOR_THEME.input_border, 1)
        value = str(getattr(chat, "current_input", "") if chat is not None else "")
        draw_text_cached(
            _truncate(value or "Ask Claude to stage a proposal...", max(1, int(width / 6.0))),
            left + 6,
            bottom + 8,
            color=EDITOR_THEME.text_primary if value else EDITOR_THEME.text_dim,
            font_size=10,
            cache=self._text_cache,
        )

    def _draw_button(self, rect: tuple[float, float, float, float], label: str, color: Any) -> None:
        left, bottom, width, height = rect
        _draw_tb_rectangle_filled(left, left + width, bottom + height, bottom, EDITOR_THEME.input_bg)
        _draw_tb_rectangle_outline(left, left + width, bottom + height, bottom, EDITOR_THEME.input_border, 1)
        draw_text_cached(
            label,
            left + (width / 2),
            bottom + (height / 2),
            color=color,
            font_size=10,
            anchor_x="center",
            anchor_y="center",
            cache=self._text_cache,
        )

    def _is_active_tab(self, controller: Any) -> bool:
        dock_ctl = getattr(controller, "dock", None)
        snapshot = dock_ctl.get_snapshot() if dock_ctl is not None and hasattr(dock_ctl, "get_snapshot") else dock_ctl
        return (getattr(snapshot, "right_tab", "Inspector") or "Inspector") == "AI Chat"


def _contains(rect: tuple[float, float, float, float], x: float, y: float) -> bool:
    left, bottom, width, height = rect
    return left <= x <= left + width and bottom <= y <= bottom + height


def build_transcript_lines(messages: list[Any], max_chars: int) -> list[dict[str, Any]]:
    width = max(1, int(max_chars))
    lines: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role", "system") or "system")
        status = message.get("status")
        text = str(message.get("text", "") or "")
        for wrapped in wrap_transcript_text(f"{role}: {text}", width):
            line = {"role": role, "text": wrapped}
            if status is not None:
                line["status"] = status
            lines.append(line)
    return lines


def wrap_transcript_text(text: str, max_chars: int) -> list[str]:
    width = max(1, int(max_chars))
    result: list[str] = []
    for paragraph in str(text or "").splitlines() or [""]:
        words = paragraph.split()
        if not words:
            result.append("")
            continue
        current = ""
        for word in words:
            pieces = _split_long_word(word, width)
            for piece in pieces:
                candidate = piece if not current else f"{current} {piece}"
                if len(candidate) <= width:
                    current = candidate
                    continue
                if current:
                    result.append(current)
                current = piece
        if current:
            result.append(current)
    return result or [""]


def _split_long_word(word: str, width: int) -> list[str]:
    value = str(word)
    if len(value) <= width:
        return [value]
    return [value[index : index + width] for index in range(0, len(value), width)]


def _truncate(value: str, limit: int) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return text[: limit - 3] + "..."
