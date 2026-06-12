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


class EntityPanelsOverlay(UIElement):
    """Editor-only overlay for the left-dock Outliner panel."""

    def draw(self) -> None:
        controller = getattr(self.window, "editor_controller", None)
        if controller is None or not getattr(controller, "active", False):
            return
        if not getattr(controller, "entity_panels_active", False):
            return

        dock = getattr(controller, "dock", None)
        snapshot = dock.get_snapshot() if dock is not None and hasattr(dock, "get_snapshot") else dock
        left_dock_tab = getattr(snapshot, "left_tab", "Outliner") or "Outliner"
        if left_dock_tab != "Outliner":
            return

        from ..editor.editor_dock_query import get_effective_dock_widths
        from ..editor.editor_shell_layout import TAB_HEADER_HEIGHT, compute_editor_shell_layout

        window_w = int(getattr(self.window, "width", 1280) or 1280)
        window_h = int(getattr(self.window, "height", 720) or 720)
        left_w, right_w = get_effective_dock_widths(controller, window_w)
        layout = compute_editor_shell_layout(window_w, window_h, left_w, right_w)
        dock_rect = layout.left_dock
        outliner_lines = controller._entity_panels_outliner_lines()
        self._draw_outliner_panel(
            outliner_lines,
            dock_rect.left + 8.0,
            dock_rect.top - TAB_HEADER_HEIGHT - 8.0,
            max(0.0, dock_rect.width - 16.0),
        )

    def _outliner_line_color(self, line: str) -> Any:
        return _line_color(line)

    def _draw_outliner_panel(self, lines: list[str], start_x: float, start_y: float, width: float) -> None:
        if not lines:
            return

        # OUTLINER rows are preformatted by engine.editor.entity_panels; keep
        # those strings intact and migrate only the render composition.
        from ..editor.widgets.panel_primitives import EditorPanelBase, PanelField, PanelRow
        from .widgets import Rect

        line_height = 18.0
        height = max(60.0, 20.0 + line_height * float(len(lines)))
        draw_panel_bg(
            start_x - 10.0,
            start_x + width,
            start_y - height,
            start_y + 20.0,
        )
        rows_panel = EditorPanelBase(
            Rect(
                x=float(start_x),
                y=float(start_y - height),
                width=float(width),
                height=float(height),
            ),
            panel_bg=(0, 0, 0, 0),
            panel_border=(0, 0, 0, 0),
            item_spacing=0.0,
            inner_padding_x=0.0,
            inner_padding_y=0.0,
        )
        for line in lines:
            field = PanelField(
                label=line,
                value=None,
                label_color=self._outliner_line_color(line),
                label_font_size=12,
            )
            rows_panel.add_row(PanelRow(content=field, height=line_height, padding_x=0.0))
        rows_panel.draw()

