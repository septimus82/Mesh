"""Component Inspector Overlay - renders collapsible component sections in right dock.

This overlay renders the Component Inspector v1 UI including:
- Collapsible component sections (Transform, Render, Interaction, Dialogue, LightSource)
- Field rows with labels and editable values
- Cursor highlight for current row
- Text edit mode with buffer display

Draws ONLY when:
- Editor mode is active
- Right dock tab is "Inspector"
- An entity is selected
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

import engine.optional_arcade as optional_arcade

from ..text_draw import draw_text_cached, TextCache
from .common import UIElement, draw_panel_bg
from ..editor.editor_shell_layout import (
    compute_editor_shell_layout,
    EditorShellLayout,
    TAB_HEADER_HEIGHT,
)
from ..editor.editor_dock_query import get_raw_dock_widths
from ..editor.inspector_components_model import (
    ComponentSection,
    ComponentRow,
    InspectorCursor,
    build_inspector_sections,
    format_field_value,
)

if TYPE_CHECKING:  # pragma: no cover
    from ..game import GameWindow


# Colors
INSPECTOR_BG_COLOR = (30, 30, 35, 255)
INSPECTOR_SECTION_HEADER_BG = (45, 45, 55, 255)
INSPECTOR_SECTION_HEADER_TEXT = (200, 200, 200, 255)
INSPECTOR_FIELD_LABEL_COLOR = (160, 160, 170, 255)
INSPECTOR_FIELD_VALUE_COLOR = (220, 220, 230, 255)
INSPECTOR_CURSOR_BG = (70, 100, 140, 180)
INSPECTOR_EDITABLE_COLOR = (100, 180, 255, 255)
INSPECTOR_READONLY_COLOR = (140, 140, 150, 255)
INSPECTOR_TEXT_EDIT_BG = (60, 80, 100, 255)
INSPECTOR_CARET_EXPAND = "[v]"
INSPECTOR_CARET_COLLAPSE = "[>]"

# Layout constants
LINE_HEIGHT = 20.0
SECTION_HEADER_HEIGHT = 24.0
FIELD_INDENT = 16.0
LABEL_WIDTH_RATIO = 0.4  # Label takes 40% of row width
PADDING = 8.0


class ComponentInspectorOverlay(UIElement):
    """Editor-only overlay that draws the component inspector in the right dock."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self._text_cache = TextCache(max_size=256)
        self._cached_layout: EditorShellLayout | None = None
        self._cached_size: tuple[int, int] = (0, 0)
        self._cached_dock_widths: tuple[int, int] = (320, 320)

    def on_resize(self, width: int, height: int) -> None:
        """Invalidate cached layout on resize."""
        self._cached_layout = None
        self._cached_size = (0, 0)

    def _get_dock_widths(self) -> tuple[int, int]:
        """Get dock widths from controller."""
        controller = getattr(self.window, "editor_controller", None)
        if controller is None:
            return (320, 320)
        return get_raw_dock_widths(controller)

    def _get_layout(self) -> EditorShellLayout:
        """Get or compute the current layout."""
        size = (self.window.width, self.window.height)
        dock_widths = self._get_dock_widths()
        if (
            self._cached_layout is None
            or self._cached_size != size
            or self._cached_dock_widths != dock_widths
        ):
            self._cached_layout = compute_editor_shell_layout(
                size[0], size[1], dock_widths[0], dock_widths[1]
            )
            self._cached_size = size
            self._cached_dock_widths = dock_widths
        return self._cached_layout

    def draw(self) -> None:
        controller = getattr(self.window, "editor_controller", None)
        if controller is None or not getattr(controller, "active", False):
            return

        # Only draw when Inspector tab is active
        dock = getattr(controller, "dock", None)
        snapshot = dock.get_snapshot() if dock is not None and hasattr(dock, "get_snapshot") else dock
        right_dock_tab = getattr(snapshot, "right_tab", "Inspector") or "Inspector"
        if right_dock_tab != "Inspector":
            return

        # Get selected entity data
        entity_json = self._get_selected_entity_json(controller)
        if entity_json is None:
            self._draw_no_selection()
            return

        # Get inspector state from controller
        expanded_state: Dict[str, bool] = getattr(
            controller, "_inspector_sections_expanded", {}
        )
        cursor_tuple = getattr(controller, "_inspector_cursor", ("transform", 0))
        cursor = InspectorCursor(section_id=cursor_tuple[0], row_index=cursor_tuple[1])
        text_edit_active: bool = getattr(controller, "_inspector_text_edit_active", False)
        text_buffer: str = getattr(controller, "_inspector_text_buffer", "")

        # Build sections
        sections = build_inspector_sections(entity_json, None, expanded_state)

        # Draw
        layout = self._get_layout()
        self._draw_sections(layout, sections, cursor, text_edit_active, text_buffer)

    def _get_selected_entity_json(self, controller: Any) -> Optional[Dict[str, Any]]:
        """Get the JSON data for the currently selected entity."""
        # Try to get primary selected entity
        primary_id = getattr(controller, "_primary_selected_id", None)
        if not primary_id:
            # Try old single selection
            selected_name = getattr(controller, "selected_entity", None)
            if not selected_name:
                return None
            primary_id = selected_name

        # Get entity data from scene controller
        scene_controller = getattr(self.window, "scene_controller", None)
        if scene_controller is None:
            return None

        # Try to get entity JSON from scene data
        loaded_data = getattr(scene_controller, "_loaded_scene_data", None)
        if not isinstance(loaded_data, dict):
            return None

        entities = loaded_data.get("entities", [])
        for ent in entities:
            if isinstance(ent, dict):
                ent_id = ent.get("id") or ent.get("mesh_name") or ent.get("name")
                if ent_id == primary_id:
                    return ent

        return None

    def _draw_no_selection(self) -> None:
        """Draw placeholder when no entity is selected."""
        layout = self._get_layout()
        dock = layout.right_dock
        content_top = dock.top - TAB_HEADER_HEIGHT - PADDING

        draw_text_cached(
            "No entity selected",
            dock.left + PADDING,
            content_top - LINE_HEIGHT,
            color=INSPECTOR_FIELD_LABEL_COLOR,
            font_size=11,
            cache=self._text_cache,
        )

    def _draw_sections(
        self,
        layout: EditorShellLayout,
        sections: List[ComponentSection],
        cursor: InspectorCursor,
        text_edit_active: bool,
        text_buffer: str,
    ) -> None:
        """Draw all inspector sections."""
        dock = layout.right_dock
        content_top = dock.top - TAB_HEADER_HEIGHT - PADDING
        content_left = dock.left + PADDING
        content_width = dock.width - 2 * PADDING

        y = content_top

        for section in sections:
            y = self._draw_section(
                section,
                content_left,
                y,
                content_width,
                cursor,
                text_edit_active,
                text_buffer,
            )

            # Stop if we've gone off the bottom
            if y < dock.bottom + PADDING:
                break

    def _draw_section(
        self,
        section: ComponentSection,
        left: float,
        top: float,
        width: float,
        cursor: InspectorCursor,
        text_edit_active: bool,
        text_buffer: str,
    ) -> float:
        """Draw a single section. Returns the Y position after drawing."""
        y = top
        is_cursor_section = cursor.section_id == section.id

        for row_idx, row in enumerate(section.visible_rows):
            is_cursor_row = is_cursor_section and cursor.row_index == row_idx

            if row.kind == "header":
                y = self._draw_header_row(
                    section, left, y, width, is_cursor_row
                )
            else:
                y = self._draw_field_row(
                    row,
                    left,
                    y,
                    width,
                    is_cursor_row,
                    text_edit_active and is_cursor_row,
                    text_buffer,
                )

        return y

    def _draw_header_row(
        self,
        section: ComponentSection,
        left: float,
        top: float,
        width: float,
        is_cursor: bool,
    ) -> float:
        """Draw a section header row. Returns Y position after drawing."""
        row_bottom = top - SECTION_HEADER_HEIGHT

        # Header background
        bg_color = INSPECTOR_CURSOR_BG if is_cursor else INSPECTOR_SECTION_HEADER_BG
        draw_panel_bg(left, left + width, row_bottom, top, bg_color)

        # Caret glyph
        caret = INSPECTOR_CARET_EXPAND if section.expanded else INSPECTOR_CARET_COLLAPSE
        caret_x = left + 4

        draw_text_cached(
            caret,
            caret_x,
            (top + row_bottom) / 2,
            color=INSPECTOR_SECTION_HEADER_TEXT,
            font_size=10,
            font_name="Consolas",
            anchor_y="center",
            cache=self._text_cache,
        )

        # Section title
        title_x = left + 28

        draw_text_cached(
            section.title,
            title_x,
            (top + row_bottom) / 2,
            color=INSPECTOR_SECTION_HEADER_TEXT,
            font_size=11,
            bold=True,
            anchor_y="center",
            cache=self._text_cache,
        )

        return row_bottom

    def _draw_field_row(
        self,
        row: ComponentRow,
        left: float,
        top: float,
        width: float,
        is_cursor: bool,
        is_editing: bool,
        text_buffer: str,
    ) -> float:
        """Draw a field row. Returns Y position after drawing."""
        row_bottom = top - LINE_HEIGHT
        field_left = left + FIELD_INDENT
        field_width = width - FIELD_INDENT

        # Row background when cursor
        if is_cursor:
            bg_color = INSPECTOR_TEXT_EDIT_BG if is_editing else INSPECTOR_CURSOR_BG
            draw_panel_bg(field_left, left + width, row_bottom, top, bg_color)

        # Label
        label_width = field_width * LABEL_WIDTH_RATIO
        label_x = field_left + 2
        label_y = (top + row_bottom) / 2

        draw_text_cached(
            row.label,
            label_x,
            label_y,
            color=INSPECTOR_FIELD_LABEL_COLOR,
            font_size=10,
            anchor_y="center",
            cache=self._text_cache,
        )

        # Value
        value_x = field_left + label_width
        value_text = text_buffer if is_editing else format_field_value(row.value, row.field_kind)
        value_color = (
            INSPECTOR_EDITABLE_COLOR
            if row.editable
            else INSPECTOR_READONLY_COLOR
        )

        # Add cursor indicator for text editing
        if is_editing:
            value_text = value_text + "_"

        draw_text_cached(
            value_text,
            value_x,
            label_y,
            color=value_color,
            font_size=10,
            anchor_y="center",
            cache=self._text_cache,
        )

        # Type hint for editable fields
        if is_cursor and row.editable and not is_editing:
            hint = self._get_edit_hint(row.field_kind)
            if hint:
                hint_x = left + width - 4
                draw_text_cached(
                    hint,
                    hint_x,
                    label_y,
                    color=INSPECTOR_FIELD_LABEL_COLOR,
                    font_size=8,
                    anchor_x="right",
                    anchor_y="center",
                    cache=self._text_cache,
                )

        return row_bottom

    def _get_edit_hint(self, field_kind: str) -> str:
        """Get edit hint text for field kind."""
        if field_kind in ("float", "int"):
            return "←/→ adjust"
        if field_kind == "string":
            return "Enter edit"
        if field_kind == "bool":
            return "Enter toggle"
        return ""
