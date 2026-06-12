from __future__ import annotations

from typing import TYPE_CHECKING, Any

import engine.optional_arcade as optional_arcade

from .common import UIElement, draw_panel_bg

if TYPE_CHECKING:  # pragma: no cover
    pass


def _line_color(line: str) -> Any:
    if line.startswith("> "):
        return optional_arcade.arcade.color.CYAN
    if line.startswith("* "):
        return optional_arcade.arcade.color.YELLOW
    return optional_arcade.arcade.color.WHITE


class SceneSwitcherOverlay(UIElement):
    """Editor-only overlay for the scene quick switcher."""

    def draw(self) -> None:
        controller = getattr(self.window, "editor_controller", None)
        if controller is None or not getattr(controller, "active", False):
            return
        if not getattr(controller, "scene_switcher_active", False):
            return

        lines = controller._scene_switcher_lines()
        if not lines:
            return

        line_height = 18.0
        height = max(80.0, 20.0 + line_height * float(len(lines)))
        width = min(720.0, max(420.0, float(self.window.width) * 0.6))

        left = (float(self.window.width) - width) / 2.0
        right = left + width
        bottom = (float(self.window.height) - height) / 2.0
        top = bottom + height

        draw_panel_bg(left, right, bottom, top)

        start_x = left + 20.0
        start_y = top - 20.0
        for i, line in enumerate(lines):
            optional_arcade.arcade.draw_text(
                line,
                start_x,
                start_y - (i * line_height),
                _line_color(line),
                12,
                font_name="Consolas",
            )
