from __future__ import annotations

from typing import TYPE_CHECKING

import engine.optional_arcade as optional_arcade
from engine.editor.editor_modal_state_query import is_scene_browser_active

from ..logging_tools import get_logger
from .state import apply_selection

if TYPE_CHECKING:
    from engine.editor_controller import EditorModeController as EditorController

logger = get_logger(__name__)


def handle_mouse_click(controller: EditorController, x: float, y: float, button: int, modifiers: int) -> bool:
    if not controller.active:
        return False

    # Project Explorer context menu (modal)
    project_explorer = getattr(controller, "project_explorer", None)
    from engine.editor.editor_panels_query import panels_is_open  # noqa: PLC0415

    if project_explorer is not None and panels_is_open(controller, "project_context_menu"):
        handler = getattr(project_explorer, "handle_context_menu_mouse_press", None)
        if callable(handler):
            return bool(handler(x, y, button, controller))
        return True

    # Menu bar handling (check first for top-level UI)
    if button == optional_arcade.arcade.MOUSE_BUTTON_LEFT:
        menu_result = _handle_menu_bar_click(controller, x, y)
        if menu_result is not None:
            return menu_result

        # Top bar dock/maximize controls (before dock splitter/tabs)
        topbar_result = _handle_top_bar_controls_click(controller, x, y)
        if topbar_result is not None:
            return topbar_result

        # Dock splitter handling (before dock tabs)
        splitter_result = _handle_splitter_click(controller, x, y)
        if splitter_result is not None:
            return splitter_result

        # Dock tab handling
        dock_tab_result = _handle_dock_tab_click(controller, x, y)
        if dock_tab_result is not None:
            return dock_tab_result

        history_result = getattr(controller, "_history_handle_mouse_click", None)
        if callable(history_result):
            handled = history_result(x, y, button)
            if handled:
                return True

        problems_result = getattr(controller, "_problems_handle_mouse_click", None)
        if callable(problems_result):
            handled = problems_result(x, y, button)
            if handled:
                return True

        debug_result = getattr(controller, "_debug_handle_mouse_click", None)
        if callable(debug_result):
            handled = debug_result(x, y, button)
            if handled:
                return True

    project_result = getattr(controller, "_project_explorer_handle_mouse_click", None)
    if callable(project_result):
        handled = project_result(x, y, button, modifiers)
        if handled:
            return True

    if getattr(controller, "_find_everything_open", False):
        search = getattr(controller, "search", None)
        handler = getattr(search, "handle_find_everything_mouse_press", None)
        if callable(handler) and handler(x, y, button, modifiers):
            return True

    if getattr(controller, "asset_browser_active", False):
        asset_browser = getattr(controller, "asset_browser", None)
        handler = getattr(asset_browser, "handle_asset_browser_mouse_click", None) if asset_browser is not None else None
        if callable(handler):
            return bool(handler(x, y, button, modifiers))
        return True

    item_editor = getattr(controller, "item_editor", None)
    if item_editor is not None and _item_editor_should_route(controller, item_editor):
        handler = getattr(item_editor, "handle_item_editor_mouse_click", None)
        if callable(handler):
            return bool(handler(x, y))
        return True

    if is_scene_browser_active(controller):
        handler = getattr(controller, "_scene_browser_handle_mouse_click", None)
        if callable(handler):
            return bool(handler(x, y, button))
        return True

    if controller.shape_edit_mode:
        world_x, world_y = controller.window.screen_to_world(x, y)
        if button == optional_arcade.arcade.MOUSE_BUTTON_LEFT:
            nearest = controller.shape.nearest_shape_vertex_index(world_x, world_y)
            if nearest >= 0:
                controller.shape_drag_index = nearest
            else:
                controller.shape.add_shape_point(world_x, world_y)
            return True
        if button == optional_arcade.arcade.MOUSE_BUTTON_RIGHT:
            controller.shape.remove_shape_point()
            return True
        return True

    if controller.tile_panel_active:
        world_x, world_y = controller.window.screen_to_world(x, y)
        if button == optional_arcade.arcade.MOUSE_BUTTON_LEFT:
            controller._paint_tile_at(world_x, world_y, controller._current_tile_gid())
            return True
        if button == optional_arcade.arcade.MOUSE_BUTTON_RIGHT:
            controller._paint_tile_at(world_x, world_y, 0)
            return True

    world_x, world_y = controller.window.screen_to_world(x, y)

    if getattr(controller, "asset_place_active", False):
        if button == optional_arcade.arcade.MOUSE_BUTTON_LEFT:
            if hasattr(controller, "place_asset_at"):
                controller.place_asset_at(world_x, world_y)
            return True
        if button == optional_arcade.arcade.MOUSE_BUTTON_RIGHT:
            controller.asset_place_active = False
            return True

    if button == optional_arcade.arcade.MOUSE_BUTTON_LEFT:
        if controller.occluder_tool_active:
            if modifiers & optional_arcade.arcade.key.MOD_SHIFT:
                return bool(controller._insert_occluder_point(world_x, world_y))
            controller._handle_occluder_mouse_press(world_x, world_y)
            return True
        if controller.lights_tool_active:
            controller._handle_lights_mouse_press(world_x, world_y)
            return True
        # Palette Placement
        if controller.palette_active:
            controller.place_entity_at_mouse(x, y)
            return True

        # Path Tool Logic
        if controller.tool_mode == "PATH" and controller.selected_entity:
            patrol = controller._get_patrol_behaviour(controller.selected_entity)
            if patrol:
                # Check for click on existing waypoint
                points = controller._get_patrol_points(patrol)
                clicked_index = -1
                for i, (px, py) in enumerate(points):
                    # Simple distance check (handle radius ~8px)
                    if (px - world_x) ** 2 + (py - world_y) ** 2 < 64:
                        clicked_index = i
                        break

                if clicked_index != -1:
                    controller.selected_waypoint_index = clicked_index
                    logger.info("[Editor] Selected waypoint %s", clicked_index)
                    return True

                # Shift+Click to add waypoint
                if modifiers & optional_arcade.arcade.key.MOD_SHIFT:
                    grid = controller.grid_size
                    snap_x = round(world_x / grid) * grid
                    snap_y = round(world_y / grid) * grid
                    controller._add_waypoint(patrol, snap_x, snap_y)
                    controller.selected_waypoint_index = len(points) - 1  # Select new one
                    return True

        # Default Selection Logic
        candidates = []
        for sprite in controller.window.scene_controller.all_sprites:
            if sprite.collides_with_point((world_x, world_y)):
                candidates.append(sprite)

        shift_held = bool(modifiers & optional_arcade.arcade.key.MOD_SHIFT)
        alt_held = bool(modifiers & optional_arcade.arcade.key.MOD_ALT)
        if candidates:
            # Pick the one drawn last (on top)
            clicked_sprite = candidates[-1]
            clicked_entity_data = getattr(clicked_sprite, "mesh_entity_data", None)
            clicked_entity_id = None
            if isinstance(clicked_entity_data, dict):
                clicked_entity_id = (
                    clicked_entity_data.get("id")
                    or clicked_entity_data.get("entity_id")
                    or clicked_entity_data.get("name")
                    or clicked_entity_data.get("mesh_name")
                )

            # Check for alt-drag duplicate
            selected_ids = list(getattr(controller, "_selected_entity_ids", []))
            if alt_held and clicked_entity_id and clicked_entity_id in selected_ids:
                from ..editor.editor_alt_drag_duplicate_ops import should_start_alt_drag_duplicate  # noqa: PLC0415
                gizmo_active = getattr(controller, "_rotate_drag_active", False) or getattr(controller, "_scale_drag_active", False)
                if should_start_alt_drag_duplicate(
                    clicked_entity_id=clicked_entity_id,
                    selected_ids=selected_ids,
                    alt_held=alt_held,
                    editor_mode_active=controller.active,
                    gizmo_active=gizmo_active,
                ):
                    controller.begin_alt_drag_duplicate(world_x, world_y)
                    return True

            apply_selection(controller, clicked_sprite, shift=shift_held)
        else:
            # Empty space click - start marquee selection instead of clearing
            from ..editor.marquee_select import should_start_marquee  # noqa: PLC0415
            if should_start_marquee(
                clicked_entity_id=None,
                clicked_gizmo=False,
                editor_mode_active=controller.active,
            ):
                controller.begin_marquee(world_x, world_y, shift_held)
            else:
                apply_selection(controller, None, shift=shift_held)

        return True
    if button == optional_arcade.arcade.MOUSE_BUTTON_RIGHT:
        # Cancel alt-drag duplicate on RMB (same as Escape)
        if getattr(controller, "_alt_dup_active", False):
            controller.cancel_alt_drag_duplicate()
            return True
        # Context menu handling
        ctx_result = _handle_context_menu_click(controller, x, y)
        if ctx_result is not None:
            return ctx_result
        if controller.occluder_tool_active:
            return bool(controller._remove_occluder_point())
    return False


def _handle_menu_bar_click(controller: EditorController, x: float, y: float) -> bool | None:
    from .editor_input_menu_handlers import handle_menu_bar_click

    return handle_menu_bar_click(controller, x, y)


def _handle_context_menu_click(controller: EditorController, x: float, y: float) -> bool | None:
    from .editor_input_menu_handlers import handle_context_menu_click

    return handle_context_menu_click(controller, x, y)


# ------------------------------------------------------------------------------
# Top Bar Controls (Dock Toggle / Maximize)
# ------------------------------------------------------------------------------


def _handle_top_bar_controls_click(controller: EditorController, x: float, y: float) -> bool | None:
    """Handle top bar dock toggle/maximize button click.

    Returns True if consumed, None to pass through.
    """
    from ..editor.editor_shell_layout import (
        compute_editor_shell_layout,
        compute_top_bar_controls,
        hit_test_top_bar_controls,
    )
    from engine.editor.editor_dock_query import get_effective_dock_widths

    # Get effective dock widths for layout
    left_w, right_w = get_effective_dock_widths(controller, controller.window.width)

    layout = compute_editor_shell_layout(
        controller.window.width,
        controller.window.height,
        left_w,
        right_w,
    )

    controls = compute_top_bar_controls(layout)
    hit = hit_test_top_bar_controls(x, y, controls)

    if hit is None:
        return None

    if hit == "toggle_left":
        dock_ctl = getattr(controller, "dock", None)
        toggle_fn = getattr(dock_ctl, "toggle_left_dock", None) if dock_ctl is not None else None
        if callable(toggle_fn):
            toggle_fn(controller)
        return True
    elif hit == "toggle_right":
        dock_ctl = getattr(controller, "dock", None)
        toggle_fn = getattr(dock_ctl, "toggle_right_dock", None) if dock_ctl is not None else None
        if callable(toggle_fn):
            toggle_fn(controller)
        return True
    elif hit == "toggle_max":
        toggle_fn = getattr(controller, "toggle_viewport_maximized", None)
        if callable(toggle_fn):
            toggle_fn()
        return True

    return None


def _item_editor_should_route(controller: EditorController, item_editor: object) -> bool:
    is_active = getattr(item_editor, "is_edit_mode_active", None)
    if not callable(is_active) or not bool(is_active()):
        return False
    dock = getattr(controller, "dock", None)
    snapshot = dock.get_snapshot() if dock is not None and hasattr(dock, "get_snapshot") else dock
    return (getattr(snapshot, "right_tab", "Inspector") or "Inspector") == "Items"


# ------------------------------------------------------------------------------
# Splitter Drag Helpers
# ------------------------------------------------------------------------------


def _handle_splitter_click(controller: EditorController, x: float, y: float) -> bool | None:
    """Handle splitter click to begin dock resize. Returns True if consumed, None to pass through."""
    from ..editor.editor_shell_layout import (
        compute_editor_shell_layout,
        hit_test_splitter,
    )
    from engine.editor.editor_dock_query import get_viewport_maximized, get_raw_dock_widths, get_dock_collapsed

    # Don't allow splitter dragging when viewport is maximized
    if get_viewport_maximized(controller):
        return None

    left_w, right_w = get_raw_dock_widths(controller)

    layout = compute_editor_shell_layout(
        controller.window.width,
        controller.window.height,
        left_w,
        right_w,
    )

    hit = hit_test_splitter(x, y, layout)
    if hit is None:
        return None

    # Don't allow dragging a splitter for a collapsed dock
    left_collapsed, right_collapsed = get_dock_collapsed(controller)
    if hit == "left" and left_collapsed:
        return None
    if hit == "right" and right_collapsed:
        return None

    dock_ctl = getattr(controller, "dock", None)
    begin_drag = getattr(dock_ctl, "begin_drag", None) if dock_ctl is not None else None
    if callable(begin_drag):
        begin_drag(controller, hit, x)
        return True

    return None


# ------------------------------------------------------------------------------
# Dock Tab Helpers
# ------------------------------------------------------------------------------


def _handle_dock_tab_click(controller: EditorController, x: float, y: float) -> bool | None:
    """Handle dock tab click. Returns True if consumed, None to pass through."""
    from ..editor.editor_shell_layout import (
        compute_editor_shell_layout,
        hit_test_dock_tab,
    )
    from engine.editor.editor_dock_query import (
        get_effective_dock_widths,
        get_viewport_maximized,
    )

    # Don't allow dock tab clicks when viewport is maximized
    if get_viewport_maximized(controller):
        return None

    # Get effective dock widths
    left_w, right_w = get_effective_dock_widths(controller, controller.window.width)

    layout = compute_editor_shell_layout(
        controller.window.width,
        controller.window.height,
        left_w,
        right_w,
    )

    hit = hit_test_dock_tab(x, y, layout)
    if hit is None:
        return None

    dock, tab_name = hit
    dock_ctl = getattr(controller, "dock", None)
    setter = getattr(dock_ctl, "apply_tab_change", None) if dock_ctl is not None else None
    if callable(setter):
        setter(controller, dock, tab_name)
        return True

    return None
