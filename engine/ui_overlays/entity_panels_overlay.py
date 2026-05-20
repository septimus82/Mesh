from __future__ import annotations

from typing import TYPE_CHECKING, Any
import engine.optional_arcade as optional_arcade

from .common import UIElement, draw_panel_bg

if TYPE_CHECKING:  # pragma: no cover
    from ..game import GameWindow


def _line_color(line: str) -> Any:
    if line.startswith("> "):
        return optional_arcade.arcade.color.CYAN
    if line.startswith("* "):
        return optional_arcade.arcade.color.YELLOW
    return optional_arcade.arcade.color.WHITE


class EntityPanelsOverlay(UIElement):
    """Editor-only overlay for Outliner/Inspector panels."""

    def draw(self) -> None:
        controller = getattr(self.window, "editor_controller", None)
        if controller is None or not getattr(controller, "active", False):
            return
        if not getattr(controller, "entity_panels_active", False):
            return

        # Check dock tab visibility
        dock = getattr(controller, "dock", None)
        snapshot = dock.get_snapshot() if dock is not None and hasattr(dock, "get_snapshot") else dock
        left_dock_tab = getattr(snapshot, "left_tab", "Outliner") or "Outliner"
        right_dock_tab = getattr(snapshot, "right_tab", "Inspector") or "Inspector"

        # Outliner only visible if left dock is set to "Outliner"
        show_outliner = left_dock_tab == "Outliner"
        # Inspector only visible if right dock is set to "Inspector"
        show_inspector = right_dock_tab == "Inspector"

        if not show_outliner and not show_inspector:
            return

        outliner_lines = controller._entity_panels_outliner_lines() if show_outliner else []
        inspector_lines = controller._entity_panels_inspector_lines() if show_inspector else []

        top = float(getattr(self.window, "height", 720) or 720) - 80.0

        if show_outliner:
            outliner_width = 320.0
            outliner_left = 20.0
            self._draw_outliner_panel(outliner_lines, outliner_left, top, outliner_width)

        if show_inspector:
            inspector_width = 360.0
            inspector_left = max(340.0, float(self.window.width) - inspector_width - 20.0)
            self._draw_inspector_panel(inspector_lines, inspector_left, top, inspector_width)

    def _outliner_line_color(self, line: str) -> Any:
        return _line_color(line)

    def _inspector_line_color(self, line: str) -> Any:
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

    def _draw_inspector_panel(self, lines: list[str], start_x: float, start_y: float, width: float) -> None:
        if not lines:
            return

        # INSPECTOR rows are preformatted by engine.editor.entity_panels; keep
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
                label_color=self._inspector_line_color(line),
                label_font_size=12,
            )
            rows_panel.add_row(PanelRow(content=field, height=line_height, padding_x=0.0))
        rows_panel.draw()

    def _draw_panel(self, lines: list[str], start_x: float, start_y: float, width: float) -> None:
        if not lines:
            return
        line_height = 18.0
        height = max(60.0, 20.0 + line_height * float(len(lines)))
        draw_panel_bg(
            start_x - 10.0,
            start_x + width,
            start_y - height,
            start_y + 20.0,
        )
        for i, line in enumerate(lines):
            optional_arcade.arcade.draw_text(
                line,
                start_x,
                start_y - (i * line_height),
                _line_color(line),
                12,
                font_name="Consolas",
            )
