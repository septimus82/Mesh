"""Debug panels overlay for editor right dock."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..text_draw import TextCache, draw_text_cached
from .common import UIElement, _draw_rectangle_filled, _draw_lrtb_rectangle_outline

if TYPE_CHECKING:  # pragma: no cover
    from ..game import GameWindow


DEBUG_TEXT_COLOR = (220, 220, 230, 255)
DEBUG_DIM_COLOR = (150, 150, 160, 255)
DEBUG_HEADER_COLOR = (180, 200, 220, 255)
DEBUG_FILTER_ACTIVE_COLOR = (255, 220, 140, 255)


class DebugPanelsOverlay(UIElement):
    """Editor-only overlay that draws debug panels (quests/cutscenes/events)."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self._text_cache = TextCache(max_size=256)

    def draw(self) -> None:
        from ..editor.debug_panels_model import (
            DEBUG_PANEL_LINE_HEIGHT,
            DEBUG_PANEL_PADDING,
            compute_debug_panel_content_bounds,
        )
        from ..editor.editor_dock_query import get_effective_dock_widths
        from ..editor.editor_shell_layout import compute_editor_shell_layout

        controller = getattr(self.window, "editor_controller", None)
        if controller is None or not getattr(controller, "active", False):
            return

        dock_ctl = getattr(controller, "dock", None)
        snapshot = dock_ctl.get_snapshot() if dock_ctl is not None and hasattr(dock_ctl, "get_snapshot") else dock_ctl
        right_tab = getattr(snapshot, "right_tab", "Inspector") or "Inspector"
        if right_tab != "Debug":
            return

        window_w = int(getattr(self.window, "width", 1280) or 1280)
        window_h = int(getattr(self.window, "height", 720) or 720)
        left_w, right_w = get_effective_dock_widths(controller, window_w)
        layout = compute_editor_shell_layout(window_w, window_h, left_w, right_w)
        dock = layout.right_dock

        # Panel framing
        _draw_rectangle_filled(
            dock.left,
            dock.right,
            dock.bottom,
            dock.top,
            (18, 18, 22, 220),
        )
        _draw_lrtb_rectangle_outline(
            dock.left,
            dock.right,
            dock.top,
            dock.bottom,
            (100, 100, 110, 255),
            1,
        )

        debug_panels = getattr(controller, "debug_panels", None)
        if debug_panels is None or not hasattr(debug_panels, "build_visible_lines"):
            return

        lines = debug_panels.build_visible_lines(window_w, window_h)
        if not lines:
            return

        padding = DEBUG_PANEL_PADDING
        line_height = DEBUG_PANEL_LINE_HEIGHT
        content_top, content_bottom, max_lines = compute_debug_panel_content_bounds(dock)
        if max_lines <= 0:
            return

        y = content_top
        for line in lines:
            draw_text_cached(
                line.text,
                dock.left + padding,
                y,
                color=_line_color(line),
                font_size=11,
                anchor_y="top",
                cache=self._text_cache,
            )
            y -= line_height
            if y < content_bottom:
                break


def _line_color(line: Any) -> Any:
    if line.kind == "header":
        return DEBUG_HEADER_COLOR
    if line.kind == "dim":
        return DEBUG_DIM_COLOR
    if line.kind == "filter_active":
        return DEBUG_FILTER_ACTIVE_COLOR
    if line.kind:
        return DEBUG_TEXT_COLOR
    text = line.text
    if text.endswith("Debug") or text in {"Diagnostics:", "Recent Events:", "Event Monitor"}:
        return DEBUG_HEADER_COLOR
    if text.startswith("...") or text.startswith("  ..."):
        return DEBUG_DIM_COLOR
    if text.startswith("No ") or text.startswith("  (none)") or text.startswith("No events"):
        return DEBUG_DIM_COLOR
    return DEBUG_TEXT_COLOR
