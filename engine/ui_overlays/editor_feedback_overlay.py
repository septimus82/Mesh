from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..text_draw import TextCache, draw_text_cached
from .common import UIElement, _draw_tb_rectangle_outline, draw_panel_bg
from .theme import EDITOR_THEME

if TYPE_CHECKING:  # pragma: no cover
    from ..editor.editor_feedback_model import FeedbackEntry, FeedbackSeverity
    from ..game import GameWindow


INFO_BG = EDITOR_THEME.severity_info_bg
INFO_BORDER = EDITOR_THEME.severity_info_border
INFO_TEXT = EDITOR_THEME.severity_info_text
WARNING_BG = EDITOR_THEME.severity_warning_bg
WARNING_BORDER = EDITOR_THEME.severity_warning_border
WARNING_TEXT = EDITOR_THEME.severity_warning_text
ERROR_BG = EDITOR_THEME.severity_error_bg
ERROR_BORDER = EDITOR_THEME.severity_error_border
ERROR_TEXT = EDITOR_THEME.severity_error_text

OVERLAY_INSET_PX = 16.0
STACK_GAP_PX = 8.0
PADDING_X = 12.0
PADDING_Y = 8.0
FONT_SIZE = 12
LINE_HEIGHT = 18.0
MIN_WIDTH = 200.0
MAX_WIDTH = 420.0
CHAR_WIDTH = 7.0


@dataclass(frozen=True, slots=True)
class FeedbackRenderItem:
    entry_id: str
    text: str
    severity: FeedbackSeverity
    left: float
    right: float
    bottom: float
    top: float
    alpha: float
    bg_color: tuple[int, int, int, int]
    border_color: tuple[int, int, int, int]
    text_color: tuple[int, int, int, int]


def format_feedback_text(entry: FeedbackEntry) -> str:
    if int(entry.count) <= 1:
        return entry.message
    return f"{entry.message} (×{int(entry.count)})"


def resolve_feedback_alpha(entry: FeedbackEntry, now: float) -> float:
    from ..editor.editor_feedback_model import FADE_OUT_WINDOW_S

    if entry.expires_at is None:
        return 1.0
    remaining = float(entry.expires_at) - float(now)
    if remaining <= 0.0:
        return 0.0
    if remaining >= FADE_OUT_WINDOW_S:
        return 1.0
    return max(0.0, remaining / FADE_OUT_WINDOW_S)


def resolve_feedback_colors(
    severity: FeedbackSeverity,
    *,
    alpha: float,
) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int], tuple[int, int, int, int]]:
    from ..editor.editor_feedback_model import FeedbackSeverity

    fade = max(0.0, min(1.0, float(alpha)))
    bg_alpha = int(round(220 * fade))
    line_alpha = int(round(255 * fade))
    text_alpha = int(round(255 * fade))
    if severity is FeedbackSeverity.WARNING:
        return (
            (*WARNING_BG, bg_alpha),
            (*WARNING_BORDER, line_alpha),
            (*WARNING_TEXT, text_alpha),
        )
    if severity is FeedbackSeverity.ERROR:
        return (
            (*ERROR_BG, bg_alpha),
            (*ERROR_BORDER, line_alpha),
            (*ERROR_TEXT, text_alpha),
        )
    return (
        (*INFO_BG, bg_alpha),
        (*INFO_BORDER, line_alpha),
        (*INFO_TEXT, text_alpha),
    )


class EditorFeedbackOverlay(UIElement):
    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self._text_cache = TextCache(max_size=32)

    def get_visible_draw_items(self, now: float | None = None) -> tuple[FeedbackRenderItem, ...]:
        from ..editor.editor_feedback_model import MAX_VISIBLE_FEEDBACK, visible_entries
        from ..editor.editor_shell_layout import compute_editor_shell_layout

        controller = getattr(self.window, "editor_controller", None)
        if controller is None or not getattr(controller, "active", False):
            return tuple()
        feedback = getattr(controller, "feedback", None)
        pending = getattr(feedback, "pending", None) if feedback is not None else None
        if not callable(pending):
            return tuple()

        entries = pending()
        if not isinstance(entries, tuple) or not entries:
            return tuple()

        current_time = float(now) if now is not None else float(getattr(feedback, "_clock", time.monotonic)())
        width = int(getattr(self.window, "width", 0) or 0)
        height = int(getattr(self.window, "height", 0) or 0)
        if width <= 0 or height <= 0:
            return tuple()

        get_widths = getattr(controller, "get_effective_dock_widths", None)
        if callable(get_widths):
            left_w, right_w = get_widths(width)
        else:
            left_w, right_w = (320, 320)
        layout = compute_editor_shell_layout(width, height, left_w, right_w)
        viewport = layout.viewport

        top = viewport.top - OVERLAY_INSET_PX
        right = viewport.right - OVERLAY_INSET_PX
        items: list[FeedbackRenderItem] = []
        for entry in visible_entries(entries, max_visible=MAX_VISIBLE_FEEDBACK):
            alpha = resolve_feedback_alpha(entry, current_time)
            if alpha <= 0.0:
                continue
            text = format_feedback_text(entry)
            text_width = len(text) * CHAR_WIDTH
            box_width = min(MAX_WIDTH, max(MIN_WIDTH, text_width + (PADDING_X * 2.0)))
            box_height = LINE_HEIGHT + (PADDING_Y * 2.0)
            left = right - box_width
            bottom = top - box_height
            bg_color, border_color, text_color = resolve_feedback_colors(entry.severity, alpha=alpha)
            items.append(
                FeedbackRenderItem(
                    entry_id=entry.id,
                    text=text,
                    severity=entry.severity,
                    left=left,
                    right=right,
                    bottom=bottom,
                    top=top,
                    alpha=alpha,
                    bg_color=bg_color,
                    border_color=border_color,
                    text_color=text_color,
                )
            )
            top = bottom - STACK_GAP_PX

        return tuple(items)

    def draw(self) -> None:
        items = self.get_visible_draw_items()
        if not items:
            return

        cache = getattr(self.window, "text_cache", None) or self._text_cache
        for item in items:
            draw_panel_bg(item.left, item.right, item.bottom, item.top, color=item.bg_color)
            _draw_tb_rectangle_outline(item.left, item.right, item.top, item.bottom, item.border_color, 2)
            draw_text_cached(
                item.text,
                item.left + PADDING_X,
                item.top - PADDING_Y,
                color=item.text_color,
                font_size=FONT_SIZE,
                anchor_y="top",
                font_name="Consolas",
                cache=cache,
            )
