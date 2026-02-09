from __future__ import annotations

from typing import TYPE_CHECKING, Any
import engine.optional_arcade as optional_arcade

from ..text_draw import TextCache, draw_text_cached
from ..editor.editor_modal_state_query import is_scene_browser_active
from .common import UIElement, draw_panel_bg

if TYPE_CHECKING:  # pragma: no cover
    from ..game import GameWindow


def _line_color(line: str) -> Any:
    if line.startswith("> "):
        return optional_arcade.arcade.color.CYAN
    if line.startswith("* "):
        return optional_arcade.arcade.color.YELLOW
    return optional_arcade.arcade.color.WHITE


class SceneBrowserOverlay(UIElement):
    """Editor-only overlay for the scene browser panel."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self._text_cache = TextCache(max_size=96)

    def draw(self) -> None:
        controller = getattr(self.window, "editor_controller", None)
        if controller is None or not getattr(controller, "active", False):
            return
        if not is_scene_browser_active(controller):
            return

        # Check dock tab visibility - Scene browser only visible if left dock is "Scene"
        dock = getattr(controller, "dock", None)
        snapshot = dock.get_snapshot() if dock is not None and hasattr(dock, "get_snapshot") else dock
        left_dock_tab = getattr(snapshot, "left_tab", "Outliner") or "Outliner"
        if left_dock_tab != "Scene":
            return

        rows = controller._scene_browser_rows()
        layout = controller._scene_browser_layout(len(rows))
        lines = controller._scene_browser_lines()
        if not lines:
            return

        draw_panel_bg(layout["left"], layout["right"], layout["bottom"], layout["top"])

        start_x = layout["start_x"]
        start_y = layout["start_y"]
        line_height = layout["line_height"]
        cache = getattr(self.window, "text_cache", None) or self._text_cache

        for i, line in enumerate(lines):
            draw_text_cached(
                line,
                start_x,
                start_y - (i * line_height),
                color=_line_color(line),
                font_size=12,
                anchor_y="top",
                cache=cache,
            )
