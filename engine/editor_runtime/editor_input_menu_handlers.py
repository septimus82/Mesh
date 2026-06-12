from __future__ import annotations

from typing import TYPE_CHECKING

import engine.optional_arcade as optional_arcade
from engine.editor.editor_modal_state_query import get_active_menu_id
from engine.editor.editor_panels_query import panels_is_open

from ..logging_tools import get_logger

if TYPE_CHECKING:
    from engine.editor_controller import EditorModeController as EditorController

logger = get_logger(__name__)


def handle_menu_bar_click(controller: EditorController, x: float, y: float) -> bool | None:
    """Handle menu bar click. Returns True if consumed, False to close menu, None to pass through."""
    from ..editor.menu_bar_model import (
        build_menu_groups,
        compute_menu_bar_layout,
        get_dropdown_bounds,
        hit_test_menu_bar,
        hit_test_menu_item,
        hit_test_menu_title,
    )

    active_menu = get_active_menu_id(controller)
    menu_groups = build_menu_groups(controller, controller.window)
    layout = compute_menu_bar_layout(
        controller.window.width,
        controller.window.height,
        menu_groups,
        active_menu,
    )

    # Check if clicking in the menu bar area
    if hit_test_menu_bar(x, y, layout):
        # Check if clicking on a menu title
        hit_title = hit_test_menu_title(x, y, layout)
        if hit_title:
            if active_menu == hit_title:
                # Clicking same title closes menu
                controller._menu_active = None
                controller._menu_hover_item_id = None
            else:
                # Open new menu
                controller._menu_active = hit_title
                controller._menu_hover_item_id = None
            return True
        return True

    # Check if clicking on a dropdown item
    if active_menu and layout.dropdown:
        hit_item = hit_test_menu_item(x, y, layout)
        if hit_item:
            # Execute the item action
            _execute_menu_item(controller, hit_item)
            controller._menu_active = None
            controller._menu_hover_item_id = None
            return True

        # Check if clicking inside dropdown bounds (but not on item)
        dropdown_bounds = get_dropdown_bounds(layout)
        if dropdown_bounds and dropdown_bounds.contains_point(x, y):
            return True  # Consume but don't close

    # If menu is active and clicking outside, close it
    if active_menu:
        controller._menu_active = None
        controller._menu_hover_item_id = None
        return True

    # Not in menu bar area, pass through
    return None


def handle_menu_bar_motion(controller: EditorController, x: float, y: float) -> bool:
    """Handle mouse motion for menu bar hover effects.

    Returns True if a menu is active and motion was handled.
    """
    active_menu = get_active_menu_id(controller)
    if not active_menu:
        return False

    from ..editor.menu_bar_model import (
        build_menu_groups,
        compute_menu_bar_layout,
        hit_test_menu_item,
        hit_test_menu_title,
    )

    menu_groups = build_menu_groups(controller, controller.window)
    layout = compute_menu_bar_layout(
        controller.window.width,
        controller.window.height,
        menu_groups,
        active_menu,
    )

    # Check if hovering over a different menu title (switch menus)
    hit_title = hit_test_menu_title(x, y, layout)
    if hit_title and hit_title != active_menu:
        controller._menu_active = hit_title
        controller._menu_hover_item_id = None
        return True

    # Update hover item
    if layout.dropdown:
        hit_item = hit_test_menu_item(x, y, layout)
        controller._menu_hover_item_id = hit_item
    else:
        controller._menu_hover_item_id = None

    return True


def handle_menu_bar_key(controller: EditorController, key: int, _modifiers: int) -> bool:
    """Handle key press for menu bar. Returns True if consumed."""
    active_menu = get_active_menu_id(controller)
    if not active_menu:
        return False

    if key == optional_arcade.arcade.key.ESCAPE:
        controller._menu_active = None
        controller._menu_hover_item_id = None
        return True

    return False


def _execute_menu_item(controller: EditorController, item_id: str) -> None:
    """Execute a menu item action."""
    from engine.editor.editor_actions import run_editor_action

    try:
        run_editor_action(item_id, controller, controller.window)
    except Exception as exc:  # noqa: BLE001  # REASON: menu action failures should log without breaking the editor input menu loop
        logger.error("[Editor] Menu action failed: %s", exc)


# ------------------------------------------------------------------------------
# Context Menu Handlers
# ------------------------------------------------------------------------------


def handle_context_menu_click(controller: EditorController, x: float, y: float) -> bool | None:
    """Handle context menu click. Returns True if consumed, False to close, None to pass through."""
    from ..editor.context_menu_model import (
        build_context_menu_items,
        compute_context_menu_layout,
        hit_test_context_menu,
        hit_test_context_menu_bounds,
    )

    context_open = panels_is_open(controller, "context_menu")

    if context_open:
        # Check if clicking inside menu
        menu_x = getattr(controller, "_context_menu_x", 0)
        menu_y = getattr(controller, "_context_menu_y", 0)
        items = build_context_menu_items(controller)
        layout = compute_context_menu_layout(
            menu_x,
            menu_y,
            items,
            controller.window.width,
            controller.window.height,
        )

        # Check if clicking on an item
        hit_item = hit_test_context_menu(x, y, layout)
        if hit_item:
            # Find the item and check if enabled
            for item, _ in layout.items_with_rects:
                if item.id == hit_item and item.enabled:
                    _execute_context_menu_item(controller, hit_item)
                    break
            _close_context_menu(controller)
            return True

        # Check if clicking inside menu bounds (but not on item)
        if hit_test_context_menu_bounds(x, y, layout):
            return True  # Consume but don't close

        # Clicking outside - close menu
        _close_context_menu(controller)
        return True

    # No menu open - check if we should open one
    # Only open if there's a selection
    if getattr(controller, "selected_entity", None) is not None:
        _open_context_menu(controller, x, y)
        return True

    return None


def _open_context_menu(controller: EditorController, x: float, y: float) -> None:
    """Open the context menu at the given screen position."""
    panels = getattr(controller, "panels", None)
    if panels is not None and hasattr(panels, "open_context_menu"):
        panels.open_context_menu()
    controller._context_menu_x = x
    controller._context_menu_y = y
    controller._context_menu_hover_id = None


def _close_context_menu(controller: EditorController) -> None:
    """Close the context menu."""
    panels = getattr(controller, "panels", None)
    if panels is not None and hasattr(panels, "close_context_menu"):
        panels.close_context_menu()
    controller._context_menu_hover_id = None


def handle_context_menu_motion(controller: EditorController, x: float, y: float) -> bool:
    """Handle mouse motion for context menu hover effects.

    Returns True if context menu is open and motion was handled.
    """
    if not panels_is_open(controller, "context_menu"):
        return False
        return False

    from ..editor.context_menu_model import (
        build_context_menu_items,
        compute_context_menu_layout,
        hit_test_context_menu,
    )

    menu_x = getattr(controller, "_context_menu_x", 0)
    menu_y = getattr(controller, "_context_menu_y", 0)
    items = build_context_menu_items(controller)
    layout = compute_context_menu_layout(
        menu_x,
        menu_y,
        items,
        controller.window.width,
        controller.window.height,
    )

    # Update hover item
    hit_item = hit_test_context_menu(x, y, layout)
    controller._context_menu_hover_id = hit_item

    return True


def handle_context_menu_key(controller: EditorController, key: int, _modifiers: int) -> bool:
    """Handle key press for context menu. Returns True if consumed."""
    if not panels_is_open(controller, "context_menu"):
        return False
        return False

    if key == optional_arcade.arcade.key.ESCAPE:
        _close_context_menu(controller)
        return True

    return False


def _execute_context_menu_item(controller: EditorController, item_id: str) -> None:
    """Execute a context menu item action."""
    if item_id == "ctx_copy":
        copier = getattr(controller, "copy_selected_entity_to_clipboard", None)
        if callable(copier):
            copier()
    elif item_id == "ctx_paste":
        paster = getattr(controller, "paste_entity_from_clipboard", None)
        if callable(paster):
            paster()
    elif item_id == "ctx_duplicate":
        duplicator = getattr(controller, "duplicate_selected", None)
        if callable(duplicator):
            duplicator()
    elif item_id == "ctx_delete":
        deleter = getattr(controller, "delete_selected", None)
        if callable(deleter):
            deleter()
    elif item_id == "ctx_focus":
        _focus_camera_on_entity(controller)
    elif item_id == "ctx_rename":
        _begin_context_rename(controller)


def _focus_camera_on_entity(controller: EditorController) -> None:
    """Center the camera on the selected entity."""
    entity = getattr(controller, "selected_entity", None)
    if entity is None:
        return

    # Get entity position
    entity_x = getattr(entity, "center_x", None)
    entity_y = getattr(entity, "center_y", None)
    if entity_x is None or entity_y is None:
        return

    # Set camera position directly
    camera_ctrl = getattr(controller.window, "camera_controller", None)
    if camera_ctrl is None:
        return

    camera = getattr(camera_ctrl, "camera", None)
    if camera is None:
        return

    # Set camera position
    try:
        camera.position = (float(entity_x), float(entity_y))
    except AttributeError:
        # Older arcade API might use center_x/center_y
        try:
            camera.center_x = float(entity_x)
            camera.center_y = float(entity_y)
        except AttributeError:
            pass

    logger.info("[Editor] Focused camera on entity at (%.1f, %.1f)", entity_x, entity_y)


def _begin_context_rename(controller: EditorController) -> None:
    """Begin renaming the selected entity via hierarchy rename mode."""
    entity = getattr(controller, "selected_entity", None)
    if entity is None:
        return

    # Activate hierarchy panel if not active
    if not getattr(controller, "hierarchy_active", False):
        toggle_hierarchy = getattr(controller, "toggle_hierarchy", None)
        if callable(toggle_hierarchy):
            toggle_hierarchy()

    # Begin rename mode
    begin_rename = getattr(controller, "_begin_hierarchy_rename", None)
    if callable(begin_rename):
        begin_rename()
