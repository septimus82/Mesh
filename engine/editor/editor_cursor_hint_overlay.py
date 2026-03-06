"""Editor cursor hint overlay.

Displays a small hint box near the mouse cursor when hovering
interactive editor elements.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import engine.optional_arcade as optional_arcade

from ..text_draw import draw_text_cached, TextCache
from ..ui_overlays.common import UIElement


_SWALLOW_ONCE_TAGS: set[str] = set()

def _log_swallow(tag: str, context: str, *, once: bool = True) -> None:
    if once and tag in _SWALLOW_ONCE_TAGS:
        return
    if once:
        _SWALLOW_ONCE_TAGS.add(tag)
    from engine.logging_tools import get_logger

    get_logger(__name__).debug("SWALLOW[%s] %s", tag, context, exc_info=True)

if TYPE_CHECKING:
    from ..game import GameWindow


# Styling constants
HINT_OFFSET_X = 12.0
HINT_OFFSET_Y = 12.0
HINT_PADDING_X = 6.0
HINT_PADDING_Y = 4.0
HINT_FONT_SIZE = 11
HINT_BG_COLOR = (30, 30, 30, 220)
HINT_TEXT_COLOR = (220, 220, 220, 255)


class EditorCursorHintOverlay(UIElement):
    """Overlay that draws cursor hint near the mouse position."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self._text_cache = TextCache(max_size=32)

    def draw(self) -> None:
        """Draw cursor hint if editor is active and hint is available."""
        controller = getattr(self.window, "editor_controller", None)
        if controller is None or not getattr(controller, "active", False):
            return

        # Get mouse position
        get_mouse_pos = getattr(controller, "get_last_mouse_pos", None)
        if not callable(get_mouse_pos):
            return

        try:
            mouse_x, mouse_y = get_mouse_pos()
        except Exception:  # noqa: BLE001
            return

        # Get hint text
        window_w = int(getattr(self.window, "width", 800) or 800)
        window_h = int(getattr(self.window, "height", 600) or 600)

        get_hint = getattr(controller, "get_cursor_hint_text", None)
        if not callable(get_hint):
            return

        try:
            hint_text = get_hint(window_w, window_h)
        except Exception:  # noqa: BLE001
            return

        if not hint_text:
            return

        # Compute hint box position (offset from cursor)
        hint_x = mouse_x + HINT_OFFSET_X
        hint_y = mouse_y + HINT_OFFSET_Y

        # Estimate text width for background
        text_width = len(hint_text) * 7  # Rough estimate
        box_width = text_width + HINT_PADDING_X * 2
        box_height = HINT_FONT_SIZE + HINT_PADDING_Y * 2

        # Clamp to screen bounds
        if hint_x + box_width > window_w:
            hint_x = mouse_x - box_width - HINT_OFFSET_X
        if hint_y + box_height > window_h:
            hint_y = mouse_y - box_height - HINT_OFFSET_Y
        if hint_x < 0:
            hint_x = 0
        if hint_y < 0:
            hint_y = 0

        # Draw background box
        box_cx = hint_x + box_width / 2
        box_cy = hint_y + box_height / 2

        try:
            optional_arcade.arcade.draw_rectangle_filled(
                box_cx, box_cy, box_width, box_height, HINT_BG_COLOR
            )
        except Exception:  # noqa: BLE001
            _log_swallow("EDIT-001", "engine/editor/editor_cursor_hint_overlay.py pass-only blanket swallow")
            pass

        # Draw text
        text_x = hint_x + HINT_PADDING_X
        text_y = hint_y + HINT_PADDING_Y

        cache = getattr(self.window, "text_cache", None) or self._text_cache

        try:
            draw_text_cached(
                hint_text,
                text_x,
                text_y,
                color=HINT_TEXT_COLOR,
                font_size=HINT_FONT_SIZE,
                anchor_x="left",
                anchor_y="bottom",
                cache=cache,
            )
        except Exception:  # noqa: BLE001
            _log_swallow("EDIT-002", "engine/editor/editor_cursor_hint_overlay.py pass-only blanket swallow")
            pass
