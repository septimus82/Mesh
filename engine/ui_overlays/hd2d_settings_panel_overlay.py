"""HD-2D Settings Panel Overlay - renders scene-level HD-2D settings in right dock.

When no entity is selected, displays an HD-2D settings panel with:
- Toggle controls for shadows, tint, outline
- Slider controls for strength/radius
- Preset buttons for quick application

When an entity IS selected, displays an "HD-2D Overrides" section with:
- Toggle controls for per-entity shadow/tint/outline overrides
- Slider controls for per-entity strength/radius
- "Inherit" state shown when override is unset
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import engine.optional_arcade as optional_arcade
from .common import UIElement
from ..text_draw import draw_text_cached, TextCache


_SWALLOW_ONCE_TAGS: set[str] = set()

def _log_swallow(tag: str, context: str, *, once: bool = True) -> None:
    if once and tag in _SWALLOW_ONCE_TAGS:
        return
    if once:
        _SWALLOW_ONCE_TAGS.add(tag)
    from engine.logging_tools import get_logger

    get_logger(__name__).debug("SWALLOW[%s] %s", tag, context, exc_info=True)

if TYPE_CHECKING:
    from engine.game import GameWindow

# Layout constants
TAB_HEADER_HEIGHT = 28.0
PADDING = 8.0
LINE_HEIGHT = 20.0
ROW_HEIGHT = 24.0
SECTION_GAP = 8.0

# Colors
PANEL_BG = (35, 35, 45, 255)
SECTION_HEADER_BG = (45, 45, 55, 255)
SECTION_HEADER_TEXT = (200, 200, 200, 255)
FIELD_LABEL_COLOR = (170, 170, 180, 255)
FIELD_VALUE_COLOR = (220, 220, 230, 255)
TOGGLE_ON_COLOR = (100, 200, 100, 255)
TOGGLE_OFF_COLOR = (180, 80, 80, 255)
TOGGLE_INHERIT_COLOR = (140, 140, 160, 255)  # Dimmer color for "inherit"
SLIDER_BG = (60, 60, 70, 255)
SLIDER_FILL = (80, 130, 200, 255)
SLIDER_INHERIT_FILL = (80, 80, 100, 255)  # Dimmer for inherit state
CURSOR_BG = (70, 90, 130, 255)
PRESET_BTN_BG = (50, 50, 60, 255)
PRESET_BTN_ACTIVE = (70, 130, 180, 255)
PRESET_BTN_TEXT = (200, 200, 210, 255)

# Toolbar button colors
TOOLBAR_BTN_BG = (50, 50, 60, 255)
TOOLBAR_BTN_DISABLED = (40, 40, 50, 255)
TOOLBAR_BTN_TEXT = (200, 200, 210, 255)
TOOLBAR_BTN_TEXT_DISABLED = (100, 100, 110, 255)

# Caret symbols
CARET_EXPAND = "▶"
CARET_COLLAPSE = "▼"


@dataclass(frozen=True, slots=True)
class Hd2dPanelRow:
    """A row in the HD-2D settings panel."""

    kind: str  # "header", "toggle", "slider", "presets"
    key: str
    label: str
    value: Any = None
    min_value: float = 0.0
    max_value: float = 1.0
    step: float = 0.05


def _build_panel_rows(settings: Dict[str, Any]) -> List[Hd2dPanelRow]:
    """Build panel rows from current settings dict."""
    return [
        # Header row for Shadows section
        Hd2dPanelRow("header", "shadows", "Shadows"),
        Hd2dPanelRow("toggle", "shadows_enabled", "Enabled", settings.get("shadows_enabled", True)),
        Hd2dPanelRow("toggle", "shadows_contact_enabled", "Contact", settings.get("shadows_contact_enabled", True)),
        Hd2dPanelRow("toggle", "shadows_ao_enabled", "Ambient Occlusion", settings.get("shadows_ao_enabled", False)),
        # Header row for Depth Tint section
        Hd2dPanelRow("header", "tint", "Depth Tint"),
        Hd2dPanelRow("toggle", "depth_tint_enabled", "Enabled", settings.get("depth_tint_enabled", False)),
        Hd2dPanelRow("slider", "depth_tint_strength", "Strength", settings.get("depth_tint_strength", 0.3), 0.0, 1.0, 0.05),
        # Header row for Outline section
        Hd2dPanelRow("header", "outline", "Outline"),
        Hd2dPanelRow("toggle", "outline_enabled", "Enabled", settings.get("outline_enabled", False)),
        Hd2dPanelRow("slider", "outline_strength", "Strength", settings.get("outline_strength", 0.5), 0.0, 1.0, 0.05),
        Hd2dPanelRow("slider", "outline_radius_px", "Radius (px)", settings.get("outline_radius_px", 1), 0, 8, 1),
        # Presets row
        Hd2dPanelRow("header", "presets", "Presets"),
        Hd2dPanelRow("presets", "preset_buttons", ""),
    ]


def format_toggle_text(value: bool) -> str:
    """Format a boolean value for display."""
    return "ON" if value else "OFF"


def format_slider_text(value: Any, is_int: bool = False) -> str:
    """Format a slider value for display."""
    if is_int:
        return str(int(value))
    return f"{float(value):.2f}"


class Hd2dSettingsPanelOverlay(UIElement):
    """Renders HD-2D scene settings in the inspector when no entity is selected."""

    def __init__(self, window: "GameWindow", *, provider: Any = None) -> None:
        super().__init__(window)
        self.provider = provider
        self._text_cache: TextCache = TextCache()
        # Panel cursor state (managed by editor_controller)
        # _hd2d_panel_cursor_index: index into flat row list
        # _hd2d_panel_sections_expanded: dict of section_key -> bool

    def _get_dock_widths(self) -> Tuple[int, int]:
        """Get current dock widths from controller."""
        controller = getattr(self.window, "editor_controller", None)
        if controller is None:
            return (320, 320)
        from ..editor.editor_dock_query import get_raw_dock_widths

        return get_raw_dock_widths(controller)

    def _get_layout(self) -> Any:
        """Get current editor layout."""
        from ..editor.editor_shell_layout import compute_editor_shell_layout

        size = (self.window.width, self.window.height)
        dock_widths = self._get_dock_widths()
        return compute_editor_shell_layout(
            size[0], size[1], dock_widths[0], dock_widths[1]
        )

    def draw(self) -> None:
        """Draw the HD-2D settings panel."""
        controller = getattr(self.window, "editor_controller", None)
        if controller is None or not getattr(controller, "active", False):
            return

        # Only draw when Inspector tab is active
        dock = getattr(controller, "dock", None)
        snapshot = dock.get_snapshot() if dock is not None and hasattr(dock, "get_snapshot") else dock
        right_dock_tab = getattr(snapshot, "right_tab", "Inspector") or "Inspector"
        if right_dock_tab != "Inspector":
            return

        # Check if any entity is selected
        primary_id = getattr(controller, "_primary_selected_id", None)
        selected_ids = getattr(controller, "_selected_entity_ids", [])
        has_selection = bool(primary_id) or (isinstance(selected_ids, list) and len(selected_ids) > 0)
        if has_selection:
            # Entity inspector takes over - don't draw
            return

        # Get provider data
        payload: Dict[str, Any] = {}
        if callable(self.provider):
            try:
                result = self.provider(self.window)
                if isinstance(result, dict):
                    payload = result
            except Exception:  # noqa: BLE001  # REASON: settings panel overlay should remain visible even if an optional provider callback fails
                _log_swallow("HDDS-001", "engine/ui_overlays/hd2d_settings_panel_overlay.py pass-only blanket swallow")
                pass

        settings = payload.get("settings", {})
        active_preset = payload.get("active_preset")
        presets = payload.get("presets", [])

        # Get panel state from controller
        cursor_index = int(getattr(controller, "_hd2d_panel_cursor_index", 0))
        sections_expanded: Dict[str, bool] = getattr(controller, "_hd2d_panel_sections_expanded", {})

        # Build rows
        rows = _build_panel_rows(settings)

        # Draw panel
        layout = self._get_layout()
        self._draw_panel(layout, rows, cursor_index, sections_expanded, active_preset, presets)

    def _draw_panel(
        self,
        layout: Any,
        rows: List[Hd2dPanelRow],
        cursor_index: int,
        sections_expanded: Dict[str, bool],
        active_preset: Optional[str],
        presets: List[Dict[str, str]],
    ) -> None:
        """Draw the full panel."""
        dock = layout.right_dock
        content_top = dock.top - TAB_HEADER_HEIGHT - PADDING
        content_left = dock.left + PADDING
        content_width = dock.width - 2 * PADDING

        # Panel title
        draw_text_cached(
            "HD-2D Scene Settings",
            content_left,
            content_top,
            color=SECTION_HEADER_TEXT,
            font_size=12,
            bold=True,
            cache=self._text_cache,
        )

        y = content_top - LINE_HEIGHT - SECTION_GAP

        # Track visible row index for cursor matching
        visible_row_idx = 0
        current_section_key: Optional[str] = None
        section_is_expanded = True

        for row in rows:
            if row.kind == "header":
                current_section_key = row.key
                section_is_expanded = sections_expanded.get(row.key, True)  # Default expanded
                is_cursor = (visible_row_idx == cursor_index)
                y = self._draw_header_row(row, content_left, y, content_width, is_cursor, section_is_expanded)
                visible_row_idx += 1
            elif section_is_expanded:
                is_cursor = (visible_row_idx == cursor_index)
                if row.kind == "toggle":
                    y = self._draw_toggle_row(row, content_left, y, content_width, is_cursor)
                elif row.kind == "slider":
                    y = self._draw_slider_row(row, content_left, y, content_width, is_cursor)
                elif row.kind == "presets":
                    y = self._draw_presets_row(content_left, y, content_width, is_cursor, active_preset, presets)
                visible_row_idx += 1

            # Stop if off screen
            if y < dock.bottom + PADDING:
                break

    def _draw_header_row(
        self,
        row: Hd2dPanelRow,
        left: float,
        top: float,
        width: float,
        is_cursor: bool,
        is_expanded: bool,
    ) -> float:
        """Draw a section header row. Returns new Y position."""
        bg_color = CURSOR_BG if is_cursor else SECTION_HEADER_BG
        optional_arcade.arcade.draw_lrtb_rectangle_filled(
            left, left + width, top, top - ROW_HEIGHT, bg_color
        )

        caret = CARET_COLLAPSE if is_expanded else CARET_EXPAND
        draw_text_cached(
            f"{caret} {row.label}",
            left + 4,
            top - ROW_HEIGHT / 2,
            color=SECTION_HEADER_TEXT,
            font_size=11,
            bold=True,
            anchor_y="center",
            cache=self._text_cache,
        )

        return top - ROW_HEIGHT - 2

    def _draw_toggle_row(
        self,
        row: Hd2dPanelRow,
        left: float,
        top: float,
        width: float,
        is_cursor: bool,
    ) -> float:
        """Draw a toggle row. Returns new Y position."""
        if is_cursor:
            optional_arcade.arcade.draw_lrtb_rectangle_filled(
                left, left + width, top, top - ROW_HEIGHT, CURSOR_BG
            )

        # Label
        draw_text_cached(
            row.label,
            left + 16,
            top - ROW_HEIGHT / 2,
            color=FIELD_LABEL_COLOR,
            font_size=10,
            anchor_y="center",
            cache=self._text_cache,
        )

        # Value
        value = bool(row.value)
        value_text = format_toggle_text(value)
        value_color = TOGGLE_ON_COLOR if value else TOGGLE_OFF_COLOR
        draw_text_cached(
            value_text,
            left + width - 40,
            top - ROW_HEIGHT / 2,
            color=value_color,
            font_size=10,
            anchor_y="center",
            cache=self._text_cache,
        )

        return top - ROW_HEIGHT - 2

    def _draw_slider_row(
        self,
        row: Hd2dPanelRow,
        left: float,
        top: float,
        width: float,
        is_cursor: bool,
    ) -> float:
        """Draw a slider row. Returns new Y position."""
        if is_cursor:
            optional_arcade.arcade.draw_lrtb_rectangle_filled(
                left, left + width, top, top - ROW_HEIGHT, CURSOR_BG
            )

        # Label
        draw_text_cached(
            row.label,
            left + 16,
            top - ROW_HEIGHT / 2,
            color=FIELD_LABEL_COLOR,
            font_size=10,
            anchor_y="center",
            cache=self._text_cache,
        )

        # Value text
        is_int = isinstance(row.step, int) or (isinstance(row.step, float) and row.step >= 1.0)
        value_text = format_slider_text(row.value, is_int)
        draw_text_cached(
            value_text,
            left + width - 40,
            top - ROW_HEIGHT / 2,
            color=FIELD_VALUE_COLOR,
            font_size=10,
            anchor_y="center",
            cache=self._text_cache,
        )

        # Slider bar
        slider_left = left + 100
        slider_width = width - 160
        slider_height = 6
        slider_y = top - ROW_HEIGHT / 2

        # Background
        optional_arcade.arcade.draw_lrtb_rectangle_filled(
            slider_left,
            slider_left + slider_width,
            slider_y + slider_height / 2,
            slider_y - slider_height / 2,
            SLIDER_BG,
        )

        # Fill
        if row.max_value > row.min_value:
            fill_ratio = (float(row.value) - row.min_value) / (row.max_value - row.min_value)
            fill_ratio = max(0.0, min(1.0, fill_ratio))
            fill_width = slider_width * fill_ratio
            optional_arcade.arcade.draw_lrtb_rectangle_filled(
                slider_left,
                slider_left + fill_width,
                slider_y + slider_height / 2,
                slider_y - slider_height / 2,
                SLIDER_FILL,
            )

        return top - ROW_HEIGHT - 2

    def _draw_presets_row(
        self,
        left: float,
        top: float,
        width: float,
        is_cursor: bool,
        active_preset: Optional[str],
        presets: List[Dict[str, str]],
    ) -> float:
        """Draw preset buttons row. Returns new Y position."""
        if is_cursor:
            optional_arcade.arcade.draw_lrtb_rectangle_filled(
                left, left + width, top, top - ROW_HEIGHT, CURSOR_BG
            )

        # Draw preset buttons horizontally
        btn_width = (width - 16) / max(len(presets), 1) - 4
        btn_height = ROW_HEIGHT - 4
        btn_y = top - ROW_HEIGHT / 2
        x = left + 8

        for preset in presets:
            preset_id = preset.get("id", "")
            preset_name = preset.get("name", "")
            is_active = (preset_id == active_preset)
            bg_color = PRESET_BTN_ACTIVE if is_active else PRESET_BTN_BG

            optional_arcade.arcade.draw_lrtb_rectangle_filled(
                x,
                x + btn_width,
                btn_y + btn_height / 2,
                btn_y - btn_height / 2,
                bg_color,
            )

            draw_text_cached(
                preset_name,
                x + btn_width / 2,
                btn_y,
                color=PRESET_BTN_TEXT,
                font_size=9,
                anchor_x="center",
                anchor_y="center",
                cache=self._text_cache,
            )

            x += btn_width + 4

        return top - ROW_HEIGHT - 2


# =============================================================================
# Entity Overrides Panel
# =============================================================================


def _build_entity_override_rows(overrides: Dict[str, Any]) -> List[Hd2dPanelRow]:
    """Build panel rows for entity overrides (None = inherit)."""
    return [
        # Header row for Shadows section
        Hd2dPanelRow("header", "shadows", "Shadows"),
        Hd2dPanelRow("override_toggle", "shadow_enabled", "Shadow", overrides.get("shadow_enabled")),
        Hd2dPanelRow("override_toggle", "shadow_contact_enabled", "Contact", overrides.get("shadow_contact_enabled")),
        Hd2dPanelRow("override_toggle", "shadow_ao_enabled", "AO", overrides.get("shadow_ao_enabled")),
        # Header row for Depth Tint section
        Hd2dPanelRow("header", "tint", "Depth Tint"),
        Hd2dPanelRow("override_toggle", "depth_tint_enabled", "Enabled", overrides.get("depth_tint_enabled")),
        Hd2dPanelRow("override_slider", "depth_tint_strength", "Strength", overrides.get("depth_tint_strength"), 0.0, 1.0, 0.05),
        # Header row for Outline section
        Hd2dPanelRow("header", "outline", "Outline"),
        Hd2dPanelRow("override_toggle", "outline_enabled", "Enabled", overrides.get("outline_enabled")),
        Hd2dPanelRow("override_slider", "outline_strength", "Strength", overrides.get("outline_strength"), 0.0, 1.0, 0.05),
        Hd2dPanelRow("override_slider", "outline_radius_px", "Radius (px)", overrides.get("outline_radius_px"), 0, 8, 1),
    ]


def format_override_toggle_text(value: bool | None) -> str:
    """Format an override toggle value for display."""
    if value is None:
        return "INHERIT"
    return "ON" if value else "OFF"


def format_override_slider_text(value: Any, is_int: bool = False) -> str:
    """Format an override slider value for display."""
    if value is None:
        return "inherit"
    if is_int:
        return str(int(value))
    return f"{float(value):.2f}"


class Hd2dEntityOverridesPanelOverlay(UIElement):
    """Renders HD-2D entity overrides in the inspector when an entity is selected."""

    def __init__(self, window: "GameWindow", *, provider: Any = None) -> None:
        super().__init__(window)
        self.provider = provider
        self._text_cache: TextCache = TextCache()

    def _get_dock_widths(self) -> Tuple[int, int]:
        """Get current dock widths from controller."""
        controller = getattr(self.window, "editor_controller", None)
        if controller is None:
            return (320, 320)
        from ..editor.editor_dock_query import get_raw_dock_widths

        return get_raw_dock_widths(controller)

    def _get_layout(self) -> Any:
        """Get current editor layout."""
        from ..editor.editor_shell_layout import compute_editor_shell_layout

        size = (self.window.width, self.window.height)
        dock_widths = self._get_dock_widths()
        return compute_editor_shell_layout(
            size[0], size[1], dock_widths[0], dock_widths[1]
        )

    def draw(self) -> None:
        """Draw the HD-2D entity overrides panel."""
        controller = getattr(self.window, "editor_controller", None)
        if controller is None or not getattr(controller, "active", False):
            return

        # Only draw when Inspector tab is active
        dock = getattr(controller, "dock", None)
        snapshot = dock.get_snapshot() if dock is not None and hasattr(dock, "get_snapshot") else dock
        right_dock_tab = getattr(snapshot, "right_tab", "Inspector") or "Inspector"
        if right_dock_tab != "Inspector":
            return

        # Only show when an entity is selected
        primary_id = getattr(controller, "_primary_selected_id", None)
        if not primary_id:
            return

        # Get provider data
        payload: Dict[str, Any] = {}
        if callable(self.provider):
            try:
                result = self.provider(self.window)
                if isinstance(result, dict):
                    payload = result
            except Exception:  # noqa: BLE001  # REASON: entity settings overlay should remain visible even if an optional provider callback fails
                _log_swallow("HDDS-002", "engine/ui_overlays/hd2d_settings_panel_overlay.py pass-only blanket swallow")
                pass

        if not payload.get("visible"):
            return

        entity_id = payload.get("entity_id", "")
        overrides = payload.get("overrides", {})
        has_overrides = payload.get("has_overrides", False)
        override_count = payload.get("override_count", 0)

        # Get panel state from controller
        cursor_index = int(getattr(controller, "_hd2d_entity_panel_cursor_index", 0))
        sections_expanded: Dict[str, bool] = getattr(controller, "_hd2d_entity_panel_sections_expanded", {})

        # Build rows
        rows = _build_entity_override_rows(overrides)

        # Draw panel
        layout = self._get_layout()
        self._draw_panel(layout, rows, cursor_index, sections_expanded, entity_id, override_count)

    def _draw_panel(
        self,
        layout: Any,
        rows: List[Hd2dPanelRow],
        cursor_index: int,
        sections_expanded: Dict[str, bool],
        entity_id: str,
        override_count: int,
    ) -> None:
        """Draw the full panel."""
        dock = layout.right_dock
        # Position below component inspector (offset by some space)
        # Use a fixed offset from bottom of dock since inspector uses top
        content_top = dock.bottom + 280  # Leave room for component inspector above
        content_left = dock.left + PADDING
        content_width = dock.width - 2 * PADDING

        # Panel title with override count
        display_id = entity_id
        if len(display_id) > 15:
            display_id = display_id[:12] + "..."
        title = f"HD-2D Overrides · {display_id}"
        if override_count > 0:
            title += f" ({override_count})"

        draw_text_cached(
            title,
            content_left,
            content_top,
            color=SECTION_HEADER_TEXT,
            font_size=11,
            bold=True,
            cache=self._text_cache,
        )

        y = content_top - LINE_HEIGHT - SECTION_GAP

        # Draw toolbar buttons (Copy / Paste / Clear)
        y = self._draw_toolbar_buttons(content_left, y, content_width, override_count)

        # Track visible row index for cursor matching
        visible_row_idx = 0
        current_section_key: Optional[str] = None
        section_is_expanded = True

        for row in rows:
            if row.kind == "header":
                current_section_key = row.key
                section_is_expanded = sections_expanded.get(row.key, True)  # Default expanded
                is_cursor = (visible_row_idx == cursor_index)
                y = self._draw_header_row(row, content_left, y, content_width, is_cursor, section_is_expanded)
                visible_row_idx += 1
            elif section_is_expanded:
                is_cursor = (visible_row_idx == cursor_index)
                if row.kind == "override_toggle":
                    y = self._draw_override_toggle_row(row, content_left, y, content_width, is_cursor)
                elif row.kind == "override_slider":
                    y = self._draw_override_slider_row(row, content_left, y, content_width, is_cursor)
                visible_row_idx += 1

            # Stop if off screen
            if y < dock.bottom + PADDING:
                break

    def _draw_toolbar_buttons(
        self,
        left: float,
        top: float,
        width: float,
        override_count: int,
    ) -> float:
        """Draw toolbar buttons (Copy / Paste / Paste+ / Clear). Returns new Y position."""
        controller = getattr(self.window, "editor_controller", None)
        clipboard = getattr(controller, "_hd2d_overrides_clipboard", None) if controller else None
        has_clipboard = isinstance(clipboard, dict) and len(clipboard) > 0
        has_overrides = override_count > 0

        # Paste = merge, Paste+ = replace (clear then apply)
        btn_labels = ["Copy", "Paste", "Paste+", "Clear"]
        btn_enabled = [True, has_clipboard, has_clipboard, has_overrides]

        btn_width = (width - 16) / len(btn_labels) - 4
        btn_height = ROW_HEIGHT - 4
        btn_y = top - ROW_HEIGHT / 2
        x = left + 8

        for i, label in enumerate(btn_labels):
            enabled = btn_enabled[i]
            bg_color = TOOLBAR_BTN_BG if enabled else TOOLBAR_BTN_DISABLED
            text_color = TOOLBAR_BTN_TEXT if enabled else TOOLBAR_BTN_TEXT_DISABLED

            optional_arcade.arcade.draw_lrtb_rectangle_filled(
                x,
                x + btn_width,
                btn_y + btn_height / 2,
                btn_y - btn_height / 2,
                bg_color,
            )

            draw_text_cached(
                label,
                x + btn_width / 2,
                btn_y,
                color=text_color,
                font_size=9,
                anchor_x="center",
                anchor_y="center",
                cache=self._text_cache,
            )

            x += btn_width + 4

        return top - ROW_HEIGHT - 4

    def _draw_header_row(
        self,
        row: Hd2dPanelRow,
        left: float,
        top: float,
        width: float,
        is_cursor: bool,
        is_expanded: bool,
    ) -> float:
        """Draw a section header row. Returns new Y position."""
        bg_color = CURSOR_BG if is_cursor else SECTION_HEADER_BG
        optional_arcade.arcade.draw_lrtb_rectangle_filled(
            left, left + width, top, top - ROW_HEIGHT, bg_color
        )

        caret = CARET_COLLAPSE if is_expanded else CARET_EXPAND
        draw_text_cached(
            f"{caret} {row.label}",
            left + 4,
            top - ROW_HEIGHT / 2,
            color=SECTION_HEADER_TEXT,
            font_size=10,
            bold=True,
            anchor_y="center",
            cache=self._text_cache,
        )

        return top - ROW_HEIGHT - 2

    def _draw_override_toggle_row(
        self,
        row: Hd2dPanelRow,
        left: float,
        top: float,
        width: float,
        is_cursor: bool,
    ) -> float:
        """Draw an override toggle row. Returns new Y position."""
        if is_cursor:
            optional_arcade.arcade.draw_lrtb_rectangle_filled(
                left, left + width, top, top - ROW_HEIGHT, CURSOR_BG
            )

        # Label
        draw_text_cached(
            row.label,
            left + 16,
            top - ROW_HEIGHT / 2,
            color=FIELD_LABEL_COLOR,
            font_size=10,
            anchor_y="center",
            cache=self._text_cache,
        )

        # Value - handle None (inherit) specially
        value = row.value
        value_text = format_override_toggle_text(value)
        if value is None:
            value_color = TOGGLE_INHERIT_COLOR
        elif value:
            value_color = TOGGLE_ON_COLOR
        else:
            value_color = TOGGLE_OFF_COLOR

        draw_text_cached(
            value_text,
            left + width - 50,
            top - ROW_HEIGHT / 2,
            color=value_color,
            font_size=10,
            anchor_y="center",
            cache=self._text_cache,
        )

        return top - ROW_HEIGHT - 2

    def _draw_override_slider_row(
        self,
        row: Hd2dPanelRow,
        left: float,
        top: float,
        width: float,
        is_cursor: bool,
    ) -> float:
        """Draw an override slider row. Returns new Y position."""
        if is_cursor:
            optional_arcade.arcade.draw_lrtb_rectangle_filled(
                left, left + width, top, top - ROW_HEIGHT, CURSOR_BG
            )

        # Label
        draw_text_cached(
            row.label,
            left + 16,
            top - ROW_HEIGHT / 2,
            color=FIELD_LABEL_COLOR,
            font_size=10,
            anchor_y="center",
            cache=self._text_cache,
        )

        # Value text - handle None (inherit) specially
        is_int = isinstance(row.step, int) or (isinstance(row.step, float) and row.step >= 1.0)
        value = row.value
        value_text = format_override_slider_text(value, is_int)
        value_color = TOGGLE_INHERIT_COLOR if value is None else FIELD_VALUE_COLOR

        draw_text_cached(
            value_text,
            left + width - 50,
            top - ROW_HEIGHT / 2,
            color=value_color,
            font_size=10,
            anchor_y="center",
            cache=self._text_cache,
        )

        # Slider bar
        slider_left = left + 90
        slider_width = width - 160
        slider_height = 5
        slider_y = top - ROW_HEIGHT / 2

        # Background
        optional_arcade.arcade.draw_lrtb_rectangle_filled(
            slider_left,
            slider_left + slider_width,
            slider_y + slider_height / 2,
            slider_y - slider_height / 2,
            SLIDER_BG,
        )

        # Fill - show inherit state differently
        if value is not None and row.max_value > row.min_value:
            fill_ratio = (float(value) - row.min_value) / (row.max_value - row.min_value)
            fill_ratio = max(0.0, min(1.0, fill_ratio))
            fill_width = slider_width * fill_ratio
            optional_arcade.arcade.draw_lrtb_rectangle_filled(
                slider_left,
                slider_left + fill_width,
                slider_y + slider_height / 2,
                slider_y - slider_height / 2,
                SLIDER_FILL,
            )

        return top - ROW_HEIGHT - 2
