"""Pure tooltip model for the editor.

This module provides deterministic, headless-safe functions for computing
tooltip text and layout based on editor state. No arcade dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from engine.editor.editor_focus_model import (
    derive_focus_target_for_controller,
    is_text_input_active_for_controller,
)
from engine.editor.editor_dock_query import get_raw_dock_widths
from engine.editor.editor_menu_hover_query import get_context_menu_hover_id
from engine.editor.editor_modal_state_query import (
    get_active_menu_id,
    is_scene_browser_active,
    is_unsaved_changes_pending,
)
from engine.editor.editor_session_query import get_session_snapshot


# Layout constants
TOOLTIP_PADDING_X = 8.0
TOOLTIP_PADDING_Y = 4.0
TOOLTIP_OFFSET_X = 12.0
TOOLTIP_OFFSET_Y = -20.0
TOOLTIP_FONT_SIZE = 11
TOOLTIP_CHAR_WIDTH = 7.0  # Approximate character width for text measurement


@dataclass(frozen=True, slots=True)
class TooltipHit:
    """Result of tooltip target hit testing.

    Attributes:
        kind: Category of the target (e.g., "dock_tab", "menu_title", "splitter").
        id: Identifier within the category (e.g., "Scene", "File", "left").
        text: The tooltip text to display.
    """

    kind: str
    id: str
    text: str


@dataclass(frozen=True, slots=True)
class TooltipLayout:
    """Layout for tooltip box.

    Attributes:
        x: Left edge X position.
        y: Bottom edge Y position.
        w: Width in pixels.
        h: Height in pixels.
    """

    x: float
    y: float
    w: float
    h: float


# Tooltip text definitions
DOCK_TAB_TOOLTIPS: Dict[str, str] = {
    "Project": "Project Explorer -- Files in the project",
    "Scene": "Scene Browser -- Search + open scenes",
    "Outliner": "Outliner -- Entities in the scene",
    "Inspector": "Inspector -- Edit selected entity",
    "Assets": "Assets -- Search + spawn assets",
    "Items": "Items -- Edit item definitions",
    "History": "History -- Undo/redo stack",
    "Problems": "Problems -- Scan + fix common issues",
    "Debug": "Debug -- Quests, cutscenes, events",
}

TOP_BAR_CONTROL_TOOLTIPS: Dict[str, str] = {
    "L": "Toggle left dock (Ctrl+L)",
    "R": "Toggle right dock (Ctrl+R)",
    "M": "Maximize viewport (Ctrl+Space)",
}

MENU_TITLE_TOOLTIPS: Dict[str, str] = {
    "File": "File -- Save, export, project actions",
    "Edit": "Edit -- Undo/redo, copy/paste, duplicate",
    "View": "View -- Panels, overlays, editor options",
}

SPLITTER_TOOLTIP = "Resize dock -- drag"


def compute_tooltip_text_for_target(kind: str, id: str) -> str | None:
    """Get tooltip text for a specific target.

    Args:
        kind: Category of the target.
        id: Identifier within the category.

    Returns:
        Tooltip text string, or None if no tooltip.
    """
    if kind == "dock_tab":
        return DOCK_TAB_TOOLTIPS.get(id)
    if kind == "menu_title":
        return MENU_TITLE_TOOLTIPS.get(id)
    if kind == "top_bar_control":
        return TOP_BAR_CONTROL_TOOLTIPS.get(id)
    if kind == "splitter":
        return SPLITTER_TOOLTIP
    if kind == "context_menu_item":
        # id is expected to be "label|shortcut" format
        return id  # Already formatted
    if kind == "inspector_field":
        # id is the field label with unit
        return id
    return None


def compute_tooltip_box_layout(
    mouse_x: float,
    mouse_y: float,
    text: str,
    window_w: int,
    window_h: int,
) -> TooltipLayout:
    """Compute tooltip box layout, clamped to window bounds.

    Args:
        mouse_x: Mouse X position in screen coordinates.
        mouse_y: Mouse Y position in screen coordinates.
        text: Tooltip text to display.
        window_w: Window width.
        window_h: Window height.

    Returns:
        TooltipLayout with position and dimensions.
    """
    # Compute box dimensions
    text_width = len(text) * TOOLTIP_CHAR_WIDTH
    box_w = text_width + TOOLTIP_PADDING_X * 2
    box_h = TOOLTIP_FONT_SIZE + TOOLTIP_PADDING_Y * 2

    # Initial position: offset from cursor (below and to the right)
    box_x = mouse_x + TOOLTIP_OFFSET_X
    box_y = mouse_y + TOOLTIP_OFFSET_Y - box_h

    # Clamp to right edge
    if box_x + box_w > window_w:
        box_x = mouse_x - box_w - TOOLTIP_OFFSET_X

    # Clamp to left edge
    if box_x < 0:
        box_x = 0

    # Clamp to bottom edge
    if box_y < 0:
        box_y = mouse_y + TOOLTIP_OFFSET_X  # Flip above cursor

    # Clamp to top edge
    if box_y + box_h > window_h:
        box_y = window_h - box_h

    return TooltipLayout(x=box_x, y=box_y, w=box_w, h=box_h)


def _is_text_input_active_state(controller: Any) -> bool:
    """Check if editor is in a text input mode (blocks tooltips).

    Args:
        controller: The editor controller.

    Returns:
        True if text input is active.
    """
    focus_target = derive_focus_target_for_controller(controller)
    return is_text_input_active_for_controller(focus_target, controller)


def _is_modal_open_state(controller: Any) -> bool:
    """Check if a modal dialog is open (blocks tooltips).

    Args:
        controller: The editor controller.

    Returns:
        True if a modal is open.
    """
    get_session_snapshot(controller)
    # Unsaved changes guard modal
    if is_unsaved_changes_pending(controller):
        return True
    # Scene browser modal (if modal mode)
    if is_scene_browser_active(controller):
        return True
    return False


def _hit_test_context_menu(
    controller: Any,
    mouse_x: float,
    mouse_y: float,
    window_w: int,
    window_h: int,
) -> TooltipHit | None:
    """Hit test for context menu item hover.

    Args:
        controller: The editor controller.
        mouse_x: Mouse X position.
        mouse_y: Mouse Y position.
        window_w: Window width.
        window_h: Window height.

    Returns:
        TooltipHit if hovering a context menu item, None otherwise.
    """
    from engine.editor.editor_panels_query import panels_is_open  # noqa: PLC0415

    if not panels_is_open(controller, "context_menu"):
        return None

    hover_id = get_context_menu_hover_id(controller)
    if not hover_id:
        return None

    # Get context menu items to find label and shortcut
    from engine.editor.context_menu_model import build_context_menu_items

    items = build_context_menu_items(controller)
    for item in items:
        if item.id == hover_id:
            if item.shortcut:
                text = f"{item.label} ({item.shortcut})"
            else:
                text = item.label
            return TooltipHit(kind="context_menu_item", id=hover_id, text=text)

    return None


def _hit_test_menu_bar(
    controller: Any,
    mouse_x: float,
    mouse_y: float,
    window_w: int,
    window_h: int,
) -> TooltipHit | None:
    """Hit test for menu bar title or item hover.

    Args:
        controller: The editor controller.
        mouse_x: Mouse X position.
        mouse_y: Mouse Y position.
        window_w: Window width.
        window_h: Window height.

    Returns:
        TooltipHit if hovering a menu title, None otherwise.
    """
    from engine.editor.menu_bar_model import (
        build_menu_groups,
        compute_menu_bar_layout,
        hit_test_menu_title,
        hit_test_menu_item,
    )

    window = getattr(controller, "window", None)
    if window is None:
        return None

    active_menu = get_active_menu_id(controller)
    groups = build_menu_groups(controller, window)
    layout = compute_menu_bar_layout(window_w, window_h, groups, active_menu)

    # Check for dropdown item hover first (higher priority)
    if active_menu and layout.dropdown:
        item_id = hit_test_menu_item(mouse_x, mouse_y, layout)
        if item_id:
            # Find the item to get label and shortcut
            for item, _ in layout.dropdown:
                if item.id == item_id:
                    if item.shortcut:
                        text = f"{item.label} ({item.shortcut})"
                    else:
                        text = item.label
                    return TooltipHit(kind="menu_item", id=item_id, text=text)

    # Check for title hover (only if no dropdown open)
    if not active_menu:
        title = hit_test_menu_title(mouse_x, mouse_y, layout)
        if title:
            tooltip_text = MENU_TITLE_TOOLTIPS.get(title)
            if tooltip_text:
                return TooltipHit(kind="menu_title", id=title, text=tooltip_text)

    return None


def _hit_test_top_bar_control(
    controller: Any,
) -> TooltipHit | None:
    """Get tooltip info for hovered top bar control.

    Args:
        controller: The editor controller.

    Returns:
        TooltipHit if hovering a top bar control, None otherwise.
    """
    from engine.editor.editor_hover_query import get_hovered_top_bar_control_id  # noqa: PLC0415

    hover_id = get_hovered_top_bar_control_id(controller)
    if not hover_id:
        return None

    tooltip_text = TOP_BAR_CONTROL_TOOLTIPS.get(hover_id)
    if not tooltip_text:
        return None

    return TooltipHit(kind="top_bar_control", id=hover_id, text=tooltip_text)


def _hit_test_splitter(
    controller: Any,
    mouse_x: float,
    mouse_y: float,
    window_w: int,
    window_h: int,
) -> TooltipHit | None:
    """Hit test for dock splitter hover.

    Args:
        controller: The editor controller.
        mouse_x: Mouse X position.
        mouse_y: Mouse Y position.
        window_w: Window width.
        window_h: Window height.

    Returns:
        TooltipHit if hovering a splitter, None otherwise.
    """
    from engine.editor.editor_shell_layout import (
        compute_editor_shell_layout,
        hit_test_splitter,
    )

    left_dock, right_dock = get_raw_dock_widths(controller)
    shell_layout = compute_editor_shell_layout(
        window_width=window_w,
        window_height=window_h,
        left_dock_w=int(left_dock),
        right_dock_w=int(right_dock),
    )

    splitter_hit = hit_test_splitter(mouse_x, mouse_y, shell_layout)
    if splitter_hit:
        return TooltipHit(kind="splitter", id=splitter_hit, text=SPLITTER_TOOLTIP)

    return None


def _hit_test_dock_tabs(
    controller: Any,
    mouse_x: float,
    mouse_y: float,
    window_w: int,
    window_h: int,
) -> TooltipHit | None:
    """Hit test for dock tab hover.

    Args:
        controller: The editor controller.
        mouse_x: Mouse X position.
        mouse_y: Mouse Y position.
        window_w: Window width.
        window_h: Window height.

    Returns:
        TooltipHit if hovering a dock tab, None otherwise.
    """
    from engine.editor.editor_shell_layout import (
        compute_editor_shell_layout,
        compute_dock_tab_rects,
    )

    left_dock, right_dock = get_raw_dock_widths(controller)
    shell_layout = compute_editor_shell_layout(
        window_width=window_w,
        window_height=window_h,
        left_dock_w=int(left_dock),
        right_dock_w=int(right_dock),
    )

    tab_rects = compute_dock_tab_rects(shell_layout)

    # Check left dock tabs
    for tab_name, rect in tab_rects.left_tab_rects.items():
        if rect.contains_point(mouse_x, mouse_y):
            tooltip_text = DOCK_TAB_TOOLTIPS.get(tab_name)
            if tooltip_text:
                return TooltipHit(kind="dock_tab", id=tab_name, text=tooltip_text)

    # Check right dock tabs
    for tab_name, rect in tab_rects.right_tab_rects.items():
        if rect.contains_point(mouse_x, mouse_y):
            tooltip_text = DOCK_TAB_TOOLTIPS.get(tab_name)
            if tooltip_text:
                return TooltipHit(kind="dock_tab", id=tab_name, text=tooltip_text)

    return None


def _hit_test_inspector_field(
    controller: Any,
    mouse_x: float,
    mouse_y: float,
    window_w: int,
    window_h: int,
) -> TooltipHit | None:
    """Hit test for inspector field hover.

    Args:
        controller: The editor controller.
        mouse_x: Mouse X position.
        mouse_y: Mouse Y position.
        window_w: Window width.
        window_h: Window height.

    Returns:
        TooltipHit if hovering an inspector field, None otherwise.
    """
    # Check if inspector is visible and has a hovered field
    inspector_cursor = getattr(controller, "_inspector_cursor", None)
    if inspector_cursor is None:
        return None

    # Get the current cursor row info
    inspector_sections = getattr(controller, "_inspector_sections", None)
    if not inspector_sections:
        return None

    from engine.editor.inspector_components_model import get_cursor_row, InspectorCursor

    # Convert tuple to InspectorCursor if needed
    if isinstance(inspector_cursor, tuple):
        cursor = InspectorCursor(section_id=inspector_cursor[0], row_index=inspector_cursor[1])
    else:
        cursor = inspector_cursor

    row = get_cursor_row(cursor, inspector_sections)
    if row is None:
        return None

    # Build tooltip text based on field kind
    field_kind = getattr(row, "field_kind", None)
    label = getattr(row, "label", None)
    if not label:
        return None

    # Add unit hints for common field types
    unit_hints = {
        "position_x": "Position X (px)",
        "position_y": "Position Y (px)",
        "rotation": "Rotation (deg)",
        "scale_x": "Scale X",
        "scale_y": "Scale Y",
        "radius": "Radius (px)",
        "intensity": "Intensity",
        "color_r": "Red (0-255)",
        "color_g": "Green (0-255)",
        "color_b": "Blue (0-255)",
        "color_a": "Alpha (0-255)",
    }

    # Use the field key if available
    key = getattr(row, "key", "")
    if key in unit_hints:
        tooltip_text = unit_hints[key]
    else:
        tooltip_text = label

    return TooltipHit(kind="inspector_field", id=key or label, text=tooltip_text)


def resolve_editor_tooltip(
    controller: Any,
    mouse_x: float,
    mouse_y: float,
    window_w: int,
    window_h: int,
) -> str | None:
    """Resolve the tooltip text based on current editor state and mouse position.

    Priority order (top wins):
    1. Modal open / text input active -> None
    2. Context menu open + hover row -> context row tooltip
    3. Menu bar hover -> menu title tooltip
    4. Top bar control hover -> control tooltip
    5. Splitter hover -> resize tooltip
    6. Dock tab hover -> dock tooltip
    7. Inspector hover field -> field tooltip
    8. None -> None

    Args:
        controller: The editor controller.
        mouse_x: Mouse X position in screen coordinates.
        mouse_y: Mouse Y position in screen coordinates.
        window_w: Window width.
        window_h: Window height.

    Returns:
        Tooltip text string, or None if no tooltip should be shown.
    """
    # Priority 1: Modal or text input blocks tooltips
    if _is_text_input_active_state(controller):
        return None
    if _is_modal_open_state(controller):
        return None

    # Priority 2: Context menu hover
    hit = _hit_test_context_menu(controller, mouse_x, mouse_y, window_w, window_h)
    if hit:
        return hit.text

    # Priority 3: Menu bar hover
    hit = _hit_test_menu_bar(controller, mouse_x, mouse_y, window_w, window_h)
    if hit:
        return hit.text

    # Priority 4: Top bar control hover
    hit = _hit_test_top_bar_control(controller)
    if hit:
        return hit.text

    # Priority 5: Splitter hover
    hit = _hit_test_splitter(controller, mouse_x, mouse_y, window_w, window_h)
    if hit:
        return hit.text

    # Priority 6: Dock tab hover
    hit = _hit_test_dock_tabs(controller, mouse_x, mouse_y, window_w, window_h)
    if hit:
        return hit.text

    # Priority 7: Inspector field hover
    hit = _hit_test_inspector_field(controller, mouse_x, mouse_y, window_w, window_h)
    if hit:
        return hit.text

    # No tooltip
    return None
