from __future__ import annotations

from typing import TYPE_CHECKING

import engine.optional_arcade as optional_arcade

from ..editor_status import build_editor_status
from ..text_draw import TextCache, draw_text_cached
from .common import UIElement, draw_panel_bg

if TYPE_CHECKING:  # pragma: no cover
    from ..game import GameWindow


class EditorStatusBarOverlay(UIElement):
    """Editor-only status bar overlay."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self._text_cache = TextCache(max_size=64)

    def draw(self) -> None:
        controller = getattr(self.window, "editor_controller", None)
        if controller is None or not getattr(controller, "active", False):
            return

        width = float(getattr(self.window, "width", 0) or 0)
        height = float(getattr(self.window, "height", 0) or 0)
        if width <= 0:
            return

        status = build_editor_status(controller, int(width), int(height))
        bar_height = 26.0

        draw_panel_bg(0.0, width, 0.0, bar_height, color=(0, 0, 0, 200))

        left_text = f"{status['scene_label']}  {status['dirty_label']}"
        # Use operation banner if active, otherwise selection label
        operation_banner = status.get("operation_banner")
        center_text = operation_banner if operation_banner else status.get("selection_label", "")

        # Build right text: hint label with cursor hint appended if present
        hint_label: str = status.get("hint_label", "") or ""
        problems_indicator: str = status.get("problems_indicator", "") or ""
        cursor_hint: str | None = status.get("cursor_hint")
        right_parts: list[str] = []
        if hint_label:
            right_parts.append(hint_label)
        if problems_indicator:
            right_parts.append(problems_indicator)
        if cursor_hint:
            right_parts.append(cursor_hint)
        right_text = " | ".join(right_parts)

        y = bar_height / 2.0
        cache = getattr(self.window, "text_cache", None) or self._text_cache

        draw_text_cached(
            left_text,
            10.0,
            y,
            color=optional_arcade.arcade.color.WHITE,
            font_size=12,
            anchor_y="center",
            cache=cache,
        )

        if center_text:
            draw_text_cached(
                center_text,
                width / 2.0,
                y,
                color=optional_arcade.arcade.color.WHITE,
                font_size=12,
                anchor_x="center",
                anchor_y="center",
                cache=cache,
            )

        if right_text:
            draw_text_cached(
                right_text,
                width - 10.0,
                y,
                color=optional_arcade.arcade.color.WHITE,
                font_size=12,
                anchor_x="right",
                anchor_y="center",
                cache=cache,
            )
