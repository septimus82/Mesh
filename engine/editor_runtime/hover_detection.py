"""Hover detection for editor UI elements and entities.

This module provides deterministic, headless-safe hover detection that
updates the editor controller's hover state based on mouse position.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Tuple

from engine.editor.editor_dock_query import get_raw_dock_widths
from engine.editor.editor_modal_state_query import (
    get_active_menu_id,
    is_scene_browser_active,
    is_unsaved_changes_pending,
)
from engine.editor.editor_session_query import get_session_snapshot

if TYPE_CHECKING:
    from engine.editor_controller import EditorModeController


def _rect_to_tuple(rect: Any) -> Tuple[float, float, float, float] | None:
    """Convert a Rect dataclass to a tuple (x, y, w, h).

    Args:
        rect: A Rect with left, bottom, width, height properties.

    Returns:
        Tuple of (x, y, w, h) or None if rect is None.
    """
    if rect is None:
        return None
    return (
        float(getattr(rect, "left", 0)),
        float(getattr(rect, "bottom", 0)),
        float(getattr(rect, "width", 0)),
        float(getattr(rect, "height", 0)),
    )


def _is_ui_blocked(controller: "EditorModeController") -> bool:
    """Check if UI hover should be blocked.

    Args:
        controller: The editor controller.

    Returns:
        True if hover detection should be skipped.
    """
    get_session_snapshot(controller)
    # Text input modes
    if getattr(controller, "palette_filter_active", False):
        return True
    if getattr(controller, "hierarchy_filter_active", False):
        return True
    if getattr(controller, "hierarchy_rename_active", False):
        return True
    if getattr(controller, "animation_edit_active", False):
        return True
    if getattr(controller, "_inspector_text_edit_active", False):
        return True
    from engine.editor.editor_panels_query import panels_is_open  # noqa: PLC0415

    if panels_is_open(controller, "command_palette"):
        return True
    if getattr(controller, "entity_panels_filter_active", False):
        return True
    if getattr(controller, "scene_browser_filter_active", False):
        return True
    if getattr(controller, "asset_browser_filter_active", False):
        return True

    # Modal states
    if is_unsaved_changes_pending(controller):
        return True
    if panels_is_open(controller, "unsaved_confirm"):
        return True
    if is_scene_browser_active(controller):
        return True

    return False


def update_hover_state(
    controller: "EditorModeController",
    x: float,
    y: float,
    window_w: int,
    window_h: int,
) -> None:
    """Update all hover highlight state based on mouse position.

    Priority order (highest first):
    1. Context menu items (if context menu open)
    2. Menu bar items (if menu active) or menu titles
    3. Top bar controls
    4. Dock tab splitters
    5. Dock tabs
    6. Inspector fields (if inspector visible and in right dock)
    7. Entity hover (if in viewport)

    Args:
        controller: The editor controller to update.
        x: Mouse X in screen coordinates.
        y: Mouse Y in screen coordinates.
        window_w: Window width.
        window_h: Window height.
    """
    # Clear previous hover state
    controller.hover.clear_hover_state()

    # Check if UI is blocked
    if _is_ui_blocked(controller):
        return

    # Get shell layout for hit testing
    from engine.editor.editor_shell_layout import (
        compute_dock_tab_rects,
        compute_editor_shell_layout,
        hit_test_dock_tab,
        hit_test_splitter,
    )

    left_dock_w, right_dock_w = get_raw_dock_widths(controller)

    layout = compute_editor_shell_layout(
        window_w, window_h,
        left_dock_w=left_dock_w,
        right_dock_w=right_dock_w,
    )

    # 1. Context menu hover (highest priority if open)
    if _update_project_explorer_context_menu_hover(controller, x, y):
        return
    if _update_context_menu_hover(controller, x, y, window_w, window_h):
        return

    # 2. Menu bar hover
    if _update_menu_bar_hover(controller, x, y, window_w, window_h):
        return

    # 3. Top bar control hover
    from engine.editor.editor_shell_layout import (
        compute_top_bar_controls,
        hit_test_top_bar_controls,
    )

    controls = compute_top_bar_controls(layout)
    top_bar_hit = hit_test_top_bar_controls(x, y, controls)
    if top_bar_hit:
        control_ids = {
            "toggle_left": "L",
            "toggle_right": "R",
            "toggle_max": "M",
        }
        controller.hover.set_hover_top_bar_control(control_ids.get(top_bar_hit))
        return

    # 4. Splitter hover
    splitter_hit = hit_test_splitter(x, y, layout)
    if splitter_hit:
        splitter_rect = layout.left_splitter if splitter_hit == "left" else layout.right_splitter
        controller.hover.set_hover_splitter(splitter_hit, _rect_to_tuple(splitter_rect))
        return

    # 5. Dock tab hover
    tab_hit = hit_test_dock_tab(x, y, layout)
    if tab_hit:
        dock_side, tab_name = tab_hit
        tab_rects = compute_dock_tab_rects(layout)
        if dock_side == "left":
            tab_rect = tab_rects.left_tab_rects.get(tab_name)
        else:
            tab_rect = tab_rects.right_tab_rects.get(tab_name)
        controller.hover.set_hover_dock_tab(dock_side, tab_name, _rect_to_tuple(tab_rect))
        return

    # 6. Inspector field hover (if in right dock and Inspector tab active)
    if _update_inspector_field_hover(controller, x, y, layout):
        return

    # 7. Entity hover (if in viewport area)
    _update_entity_hover(controller, x, y, layout)


def _update_context_menu_hover(
    controller: "EditorModeController",
    x: float,
    y: float,
    window_w: int,
    window_h: int,
) -> bool:
    """Update context menu item hover state.

    Returns True if context menu is open (regardless of hover hit).
    """
    from engine.editor.editor_panels_query import panels_is_open  # noqa: PLC0415

    if not panels_is_open(controller, "context_menu"):
        return False

    from engine.editor.context_menu_model import (
        build_context_menu_items,
        compute_context_menu_layout,
        hit_test_context_menu,
    )

    menu_x = getattr(controller, "_context_menu_x", 0)
    menu_y = getattr(controller, "_context_menu_y", 0)
    items = build_context_menu_items(controller)
    layout = compute_context_menu_layout(
        menu_x, menu_y, items, window_w, window_h
    )

    hit_item = hit_test_context_menu(x, y, layout)
    controller._context_menu_hover_id = hit_item

    # Get rect for hovered item from items_with_rects
    if hit_item and layout.items_with_rects:
        for item, rect in layout.items_with_rects:
            if item.id == hit_item:
                controller.hover.set_hover_context_item_rect(_rect_to_tuple(rect))
                break

    return True  # Context menu is open, blocks other hover


def _update_project_explorer_context_menu_hover(
    controller: "EditorModeController",
    x: float,
    y: float,
) -> bool:
    """Update hover for Project Explorer context menu if open."""
    project = getattr(controller, "project_explorer", None)
    from engine.editor.editor_panels_query import panels_is_open  # noqa: PLC0415

    if project is None or not panels_is_open(controller, "project_context_menu"):
        return False
    handler = getattr(project, "handle_context_menu_mouse_move", None)
    if callable(handler):
        handler(x, y)
    return True


def _update_menu_bar_hover(
    controller: "EditorModeController",
    x: float,
    y: float,
    window_w: int,
    window_h: int,
) -> bool:
    """Update menu bar hover state.

    Returns True if menu is active or hovering on menu title.
    """
    from engine.editor.menu_bar_model import (
        build_menu_groups,
        compute_menu_bar_layout,
        hit_test_menu_item,
        hit_test_menu_title,
    )

    active_menu = get_active_menu_id(controller)
    window = getattr(controller, "window", None)
    if window is None:
        return False

    menu_groups = build_menu_groups(controller, window)
    layout = compute_menu_bar_layout(window_w, window_h, menu_groups, active_menu)

    # If menu is active, check for item hover
    if active_menu:
        hit_item = hit_test_menu_item(x, y, layout)
        controller._menu_hover_item_id = hit_item

        # Get rect for hovered item from dropdown list
        if hit_item and layout.dropdown:
            for item, rect in layout.dropdown:
                if item.id == hit_item:
                    controller.hover.set_hover_menu_item_rect(_rect_to_tuple(rect))
                    break

        # Check for title switch
        hit_title = hit_test_menu_title(x, y, layout)
        if hit_title and hit_title != active_menu:
            controller._menu_active = hit_title
            controller._menu_hover_item_id = None

        return True

    # Menu not active - check for title hover (for highlight only)
    hit_title = hit_test_menu_title(x, y, layout)
    if hit_title:
        title_rect = layout.titles.get(hit_title) if layout.titles else None
        controller.hover.set_hover_menu_title(hit_title, _rect_to_tuple(title_rect))
        return True

    # No menu title hover; allow other hover checks to proceed.
    return False


def _update_inspector_field_hover(
    controller: "EditorModeController",
    x: float,
    y: float,
    layout: Any,
) -> bool:
    """Update inspector field hover state.

    Returns True if hovering an inspector field.
    """
    # Check if right dock is showing Inspector tab
    dock = getattr(controller, "dock", None)
    snapshot = dock.get_snapshot() if dock is not None and hasattr(dock, "get_snapshot") else dock
    right_tab = getattr(snapshot, "right_tab", "Inspector") or "Inspector"
    if right_tab != "Inspector":
        return False

    # Check if mouse is in right dock area
    right_dock = layout.right_dock
    if not right_dock.contains_point(x, y):
        return False

    # Check if we have a selection to show inspector
    selection = getattr(controller, "selected_entity_ids", None)
    if not selection:
        return False

    # Simple row-based hit test for inspector fields
    # Inspector uses fixed row height and starts below dock tabs
    from engine.editor.editor_shell_layout import TAB_HEADER_HEIGHT

    inspector_top = right_dock.top - TAB_HEADER_HEIGHT
    inspector_bottom = right_dock.bottom

    # Standard row height for inspector fields
    ROW_HEIGHT = 24.0
    PADDING = 4.0

    # Calculate which row the mouse is in
    if y > inspector_top or y < inspector_bottom:
        return False

    row_index = int((inspector_top - y) / ROW_HEIGHT)

    # Get inspector field keys - simplified approach
    # The actual fields depend on the selected entity's components
    primary_id = getattr(controller, "primary_entity_id", None)
    if not primary_id:
        return False

    # Build a simple list of field keys based on common inspector structure
    # This is a simplified version - real implementation would use actual inspector model
    field_keys = _get_inspector_field_keys(controller, primary_id)

    if row_index < 0 or row_index >= len(field_keys):
        return False

    field_key = field_keys[row_index]

    # Compute rect for this row
    row_top = inspector_top - row_index * ROW_HEIGHT
    row_bottom = row_top - ROW_HEIGHT
    rect = (right_dock.left + PADDING, row_bottom, right_dock.width - 2 * PADDING, ROW_HEIGHT - PADDING)

    controller.hover.set_hover_inspector_field(field_key, rect)

    return True


def _get_inspector_field_keys(controller: "EditorModeController", entity_id: str) -> list[str]:
    """Get list of inspector field keys for an entity.

    This returns a simplified list of field keys. A full implementation
    would query the actual inspector model for visible rows.
    """
    # Get entity data
    scene_controller = getattr(controller.window, "scene_controller", None)
    if not scene_controller:
        return []

    entity_data = None
    entities = getattr(scene_controller, "entities", None)
    iter_entities = getattr(entities, "iter_entities", None) if entities is not None else None
    if callable(iter_entities):
        try:
            sprites = iter_entities()
        except TypeError:
            sprites = iter_entities(scene_controller)
    else:
        sprites = getattr(scene_controller, "all_sprites", [])
    from engine.editor.editor_clipboard_ops import get_entity_id_from_data  # noqa: PLC0415

    for sprite in list(sprites or []):
        data = getattr(sprite, "mesh_entity_data", None)
        if not isinstance(data, dict):
            continue
        if get_entity_id_from_data(data) == entity_id:
            entity_data = data
            break

    if not entity_data:
        return []

    keys = []

    # Transform section
    keys.append("transform.header")
    keys.append("position.x")
    keys.append("position.y")
    if "rotation" in entity_data or "rotation_deg" in entity_data:
        keys.append("rotation")
    if "scale" in entity_data or "scale_x" in entity_data:
        keys.append("scale.x")
        keys.append("scale.y")

    # Sprite section (if has sprite)
    if entity_data.get("sprite") or entity_data.get("prefab"):
        keys.append("sprite.header")
        keys.append("sprite.path")

    # Light section (if has light)
    light = entity_data.get("light")
    if light:
        keys.append("light.header")
        keys.append("light.radius")
        keys.append("light.color")

    return keys


def _update_entity_hover(
    controller: "EditorModeController",
    x: float,
    y: float,
    layout: Any,
) -> bool:
    """Update entity hover state (world-space).

    Returns True if hovering an entity.
    """
    # Check if mouse is in viewport area
    viewport = layout.viewport
    if not viewport.contains_point(x, y):
        return False

    # Convert screen to world coordinates
    window = getattr(controller, "window", None)
    screen_to_world = getattr(window, "screen_to_world", None) if window else None
    if not callable(screen_to_world):
        return False

    try:
        world_x, world_y = screen_to_world(x, y)
    except Exception:
        return False

    # Get entities from scene
    scene_controller = getattr(window, "scene_controller", None) if window else None
    if not scene_controller:
        return False

    entities = getattr(scene_controller, "entities", None)
    iter_entities = getattr(entities, "iter_entities", None) if entities is not None else None
    sprites = iter_entities(scene_controller) if callable(iter_entities) else getattr(scene_controller, "all_sprites", [])
    sprite_list = getattr(scene_controller, "entity_sprites", None)

    from engine.editor.editor_clipboard_ops import get_entity_id_from_data  # noqa: PLC0415
    from engine.editor.selection_outline import resolve_entity_bounds

    # Find topmost entity under cursor
    # Prefer currently selected entity if it contains the point
    selected_ids = getattr(controller, "selected_entity_ids", None) or []
    primary_id = getattr(controller, "primary_entity_id", None)

    # Build entity lookup
    entity_by_id: dict[str, dict] = {}
    for sprite in list(sprites or []):
        data = getattr(sprite, "mesh_entity_data", None)
        if not isinstance(data, dict):
            continue
        eid = get_entity_id_from_data(data)
        if eid:
            entity_by_id[eid] = data

    # Build sprite lookup
    sprite_by_id: dict[str, Any] = {}
    if sprite_list:
        for sprite in sprite_list:
            sprite_eid = getattr(sprite, "entity_id", None)
            if isinstance(sprite_eid, str) and sprite_eid:
                sprite_by_id[sprite_eid] = sprite
    else:
        for sprite in list(sprites or []):
            data = getattr(sprite, "mesh_entity_data", None)
            if not isinstance(data, dict):
                continue
            eid = get_entity_id_from_data(data)
            if eid:
                sprite_by_id[eid] = sprite

    # First check primary selection
    if primary_id and primary_id in entity_by_id:
        entity_data = entity_by_id[primary_id]
        sprite = sprite_by_id.get(primary_id)
        rect = resolve_entity_bounds(entity_data, sprite)
        if rect and rect.contains_point(world_x, world_y):
            # Primary selection hovered - don't show hover highlight (already selected)
            return False

    # Find first entity containing point (sorted by ID for determinism)
    for eid in sorted(entity_by_id.keys()):
        # Skip already selected entities
        if eid in selected_ids:
            continue

        entity_data = entity_by_id[eid]
        sprite = sprite_by_id.get(eid)
        rect = resolve_entity_bounds(entity_data, sprite)

        if rect and rect.contains_point(world_x, world_y):
            # Found hover target
            rect_tuple = (rect.x, rect.y, rect.w, rect.h)
            controller.hover.set_hover_entity(eid, rect_tuple)
            return True

    return False
