from __future__ import annotations

from typing import Any, TYPE_CHECKING
import engine.optional_arcade as optional_arcade

from engine.editor.editor_actions import get_editor_actions, run_editor_action
from engine.editor.shortcut_resolver_model import (
    build_shortcut_map,
    build_shortcut_map_by_scope,
    normalize_shortcut_event,
    resolve_shortcut_scoped,
)
from engine.editor.editor_focus_model import (
    collect_editor_state,
    compute_active_shortcut_scopes,
    derive_focus_target,
    is_text_input_active,
)
from engine.editor.state import (
    TRANSFORM_MODE_MOVE,
    TRANSFORM_MODE_ROTATE,
    TRANSFORM_MODE_SCALE,
)

if TYPE_CHECKING:
    from engine.editor_controller import EditorModeController as EditorController

from ..logging_tools import get_logger
from .state import apply_selection

logger = get_logger(__name__)
_shortcut_conflicts_warned: set[str] = set()


def _is_text_input_active(controller: "EditorController") -> bool:
    snapshot = _get_focus_snapshot(controller)
    return bool(snapshot.get("text_input_active", False))


def _get_active_shortcut_scopes(controller: "EditorController") -> list[str]:
    snapshot = _get_focus_snapshot(controller)
    scopes = snapshot.get("scopes")
    return list(scopes) if isinstance(scopes, tuple) else list(scopes or [])


def _get_focus_snapshot(controller: "EditorController") -> dict[str, Any]:
    focus_ctl = getattr(controller, "focus", None)
    if focus_ctl is not None:
        getter = getattr(focus_ctl, "get_focus_snapshot", None)
        if callable(getter):
            result = getter()
            if isinstance(result, dict):
                return result
    state_dict = collect_editor_state(controller)
    focus_target = derive_focus_target(state_dict)
    return {
        "focus_target": focus_target,
        "text_input_active": is_text_input_active(focus_target, state_dict),
        "scopes": compute_active_shortcut_scopes(focus_target, state_dict),
    }


def _handle_editor_action_shortcut(controller: "EditorController", key: int, modifiers: int) -> bool:
    """Handle shortcut dispatch using scoped resolution.
    
    Uses shortcut scopes to resolve conflicts:
    - Scoped shortcuts (like inline rename) take priority when their scope is active
    - Global shortcuts are the fallback
    """
    shortcut = normalize_shortcut_event(key, modifiers)
    if not shortcut:
        return False
    # Skip single alphanumeric characters without modifiers (let text input handle them)
    if "+" not in shortcut and len(shortcut) == 1 and shortcut.isalnum():
        return False
    
    window = getattr(controller, "window", None)
    if window is not None and getattr(window, "editor_controller", None) is None:
        try:
            window.editor_controller = controller
        except Exception:
            pass
    
    actions = get_editor_actions(controller, window)
    scope_maps = build_shortcut_map_by_scope(actions)
    active_scopes = _get_active_shortcut_scopes(controller)
    
    # Resolve using scoped priority
    action_id = resolve_shortcut_scoped(scope_maps, shortcut, active_scopes)
    if not action_id:
        return False
    
    # Check if action is enabled
    if not _action_is_enabled(actions, action_id, controller, window):
        return False
    
    return run_editor_action(action_id, controller, window)


def _action_is_enabled(actions: list[Any], action_id: str, controller: Any, window: Any) -> bool:
    """Check if an action is enabled by its ID."""
    for action in actions:
        if getattr(action, "id", None) == action_id:
            enabled_fn = getattr(action, "enabled", None)
            if callable(enabled_fn):
                return bool(enabled_fn(controller, window))
            return True
    return False


def handle_mouse_click(controller: EditorController, x: float, y: float, button: int, modifiers: int) -> bool:
    if not controller.active:
        return False

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

        project_result = getattr(controller, "_project_explorer_handle_mouse_click", None)
        if callable(project_result):
            handled = project_result(x, y, button, modifiers)
            if handled:
                return True

    if getattr(controller, "scene_browser_active", False):
        handler = getattr(controller, "_scene_browser_handle_mouse_click", None)
        if callable(handler):
            return bool(handler(x, y, button))
        return True

    if controller.shape_edit_mode:
        world_x, world_y = controller.window.screen_to_world(x, y)
        if button == optional_arcade.arcade.MOUSE_BUTTON_LEFT:
            nearest = controller._nearest_shape_vertex_index(world_x, world_y)
            if nearest >= 0:
                controller.shape_drag_index = nearest
            else:
                controller._add_shape_point(world_x, world_y)
            return True
        if button == optional_arcade.arcade.MOUSE_BUTTON_RIGHT:
            controller._remove_shape_point()
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
                return controller._insert_occluder_point(world_x, world_y)
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
            return controller._remove_occluder_point()
    return False


def handle_input(controller: EditorController, key: int, modifiers: int) -> bool:
    """Handle keyboard input when editor is active. Returns True if consumed."""
    if not controller.active:
        return False

    # Alt-drag duplicate cancel on Escape (check early)
    if key == optional_arcade.arcade.key.ESCAPE and getattr(controller, "_alt_dup_active", False):
        controller.cancel_alt_drag_duplicate()
        return True

    # Marquee cancel on Escape (check early)
    if key == optional_arcade.arcade.key.ESCAPE and getattr(controller, "_marquee_active", False):
        controller.cancel_marquee()
        return True

    if getattr(controller, "confirm_open", False):
        handler = getattr(controller, "_handle_unsaved_confirm_input", None)
        if callable(handler):
            return bool(handler(key, modifiers))
        return True

    if key == optional_arcade.arcade.key.F and (modifiers & optional_arcade.arcade.key.MOD_CTRL):
        focus_search = getattr(controller, "focus_search_for_active_panel", None)
        if callable(focus_search) and focus_search():
            return True

    is_search_focused = getattr(controller, "is_search_focused", None)
    if callable(is_search_focused) and is_search_focused():
        if key == optional_arcade.arcade.key.ESCAPE:
            clear_search = getattr(controller, "clear_search_for_active_panel", None)
            if callable(clear_search) and clear_search():
                return True
            clear_focus = getattr(controller, "clear_search_focus", None)
            if callable(clear_focus):
                clear_focus()
            return True
        if key == optional_arcade.arcade.key.BACKSPACE:
            backspace = getattr(controller, "backspace_search_text", None)
            if callable(backspace):
                backspace()
            return True
        if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
            panel = getattr(controller, "_search_focus", None)
            if panel == "problems":
                handler = getattr(controller, "_handle_problems_input", None)
                if callable(handler):
                    handler(key, modifiers)
            return True
        if key in (
            optional_arcade.arcade.key.UP,
            optional_arcade.arcade.key.DOWN,
            optional_arcade.arcade.key.PAGE_UP,
            optional_arcade.arcade.key.PAGE_DOWN,
        ):
            panel = getattr(controller, "_search_focus", None)
            handler = None
            if panel == "outliner":
                handler = getattr(controller, "_handle_entity_panels_input", None)
            elif panel == "assets":
                handler = getattr(controller, "_handle_asset_browser_input", None)
            elif panel == "history":
                handler = getattr(controller, "_handle_history_input", None)
            elif panel == "problems":
                handler = getattr(controller, "_handle_problems_input", None)
            if callable(handler):
                handler(key, modifiers)
            return True
        return True

    if getattr(controller, "_find_everything_open", False):
        handler = getattr(controller, "_handle_find_everything_input", None)
        if callable(handler) and handler(key, modifiers):
            return True
        return True

    # Menu bar handles Escape to close
    if handle_menu_bar_key(controller, key, modifiers):
        return True

    # Context menu handles Escape to close
    if handle_context_menu_key(controller, key, modifiers):
        return True

    if getattr(controller, "asset_place_active", False):
        if key == optional_arcade.arcade.key.ESCAPE:
            controller.asset_place_active = False
            return True
        if key == optional_arcade.arcade.key.ENTER:
            mx = getattr(controller.window, "_mouse_x", 0)
            my = getattr(controller.window, "_mouse_y", 0)
            wx, wy = controller.window.screen_to_world(mx, my)
            if hasattr(controller, "place_asset_at"):
                controller.place_asset_at(wx, wy)
            return True

    if _handle_editor_action_shortcut(controller, key, modifiers):
        return True

    if getattr(controller, "scene_browser_active", False):
        handler = getattr(controller, "_handle_scene_browser_input", None)
        if callable(handler):
            return bool(handler(key, modifiers))
        return True

    if getattr(controller, "asset_browser_active", False):
        handler = getattr(controller, "_handle_asset_browser_input", None)
        if callable(handler):
            return bool(handler(key, modifiers))
        return True

    if getattr(controller, "scene_switcher_active", False):
        handler = getattr(controller, "_handle_scene_switcher_input", None)
        if callable(handler):
            return bool(handler(key, modifiers))
        return True

    if key == optional_arcade.arcade.key.J and (modifiers & optional_arcade.arcade.key.MOD_CTRL):
        if not _is_text_input_active(controller):
            return run_editor_action("editor.find_everything.toggle", controller, controller.window)
        return True

    if controller.command_palette_active:
        if key == optional_arcade.arcade.key.ESCAPE:
            controller.command_palette_active = False
            controller.command_palette_query = ""
            controller.command_palette_index = 0
            return True
        if key == optional_arcade.arcade.key.BACKSPACE:
            controller.command_palette_query = controller.command_palette_query[:-1]
            controller.command_palette_index = 0
            return True
        if key == optional_arcade.arcade.key.UP:
            idx = int(getattr(controller, "command_palette_index", 0) or 0)
            controller.command_palette_index = max(0, idx - 1)
            return True
        if key == optional_arcade.arcade.key.DOWN:
            idx = int(getattr(controller, "command_palette_index", 0) or 0)
            controller.command_palette_index = idx + 1
            return True
        if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
            from engine.editor_commands import (  # noqa: PLC0415
                filter_commands,
                get_all_commands,
                get_palette_focus_target,
            )

            focus_target = get_palette_focus_target(controller)
            commands = filter_commands(
                get_all_commands(controller.window),
                controller.command_palette_query,
                focus_target=focus_target,
            )
            if commands:
                max_items = min(len(commands), 8)
                idx = max(0, min(int(getattr(controller, "command_palette_index", 0) or 0), max_items - 1))
                commands[idx].run(controller.window)
            controller.command_palette_active = False
            controller.command_palette_query = ""
            controller.command_palette_index = 0
            return True
        return True

    if getattr(controller, "_left_dock_tab", "Outliner") == "Project":
        handler = getattr(controller, "_handle_project_explorer_input", None)
        if callable(handler) and handler(key, modifiers):
            return True

    if controller.entity_panels_active:
        handler = getattr(controller, "_handle_entity_panels_input", None)
        if callable(handler) and handler(key, modifiers):
            return True

    if getattr(controller, "_right_dock_tab", "Inspector") == "History":
        handler = getattr(controller, "_handle_history_input", None)
        if callable(handler) and handler(key, modifiers):
            return True
    if getattr(controller, "_right_dock_tab", "Inspector") == "Problems":
        handler = getattr(controller, "_handle_problems_input", None)
        if callable(handler) and handler(key, modifiers):
            return True

    # Component Inspector v1 input (when Inspector tab is active)
    if getattr(controller, "_right_dock_tab", "Inspector") == "Inspector":
        # Try v1 handler first
        v1_handler = getattr(controller, "_handle_component_inspector_v1_input", None)
        if callable(v1_handler) and v1_handler(key, modifiers):
            return True
        # Fall back to legacy handler
        inspector_handler = getattr(controller, "_handle_inspector_component_input", None)
        if callable(inspector_handler) and inspector_handler(key, modifiers):
            return True

    if key == optional_arcade.arcade.key.O and (modifiers & optional_arcade.arcade.key.MOD_SHIFT) and not (modifiers & optional_arcade.arcade.key.MOD_CTRL):
        return controller.toggle_shape_edit_mode("occluder")
    if key == optional_arcade.arcade.key.C and (modifiers & optional_arcade.arcade.key.MOD_SHIFT) and not (modifiers & optional_arcade.arcade.key.MOD_CTRL):
        return controller.toggle_shape_edit_mode("collision")
    if key == optional_arcade.arcade.key.O and not modifiers:
        return run_editor_action("editor.occluder_tool.toggle", controller, controller.window)

    if controller.shape_edit_mode:
        if key in (optional_arcade.arcade.key.ESCAPE,):
            controller._cancel_shape_edit()
            return True
        if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
            controller._commit_shape_edit()
            return True
        if key in (optional_arcade.arcade.key.BACKSPACE, optional_arcade.arcade.key.DELETE):
            return controller._remove_shape_point()
        if key == optional_arcade.arcade.key.G and not modifiers:
            controller.shape_snap_enabled = not controller.shape_snap_enabled
            return True

    if not controller.shape_edit_mode:
        if key == optional_arcade.arcade.key.G and not modifiers:
            controller.snap_enabled = not controller.snap_enabled
            return True
        if key == optional_arcade.arcade.key.G and (modifiers & optional_arcade.arcade.key.MOD_SHIFT):
            modes = ["grid8", "grid16", "tile_center"]
            try:
                idx = modes.index(controller.snap_mode)
            except ValueError:
                idx = 0
            controller.snap_mode = modes[(idx + 1) % len(modes)]
            return True

    # Transform mode hotkeys (W = Move, E = Rotate, Q = Scale)
    # Only when selected entity and no modifiers, not in text input
    if controller.selected_entity and not modifiers and not _is_text_input_active(controller):
        if key == optional_arcade.arcade.key.W:
            controller.transform_mode = TRANSFORM_MODE_MOVE
            logger.info("[Editor] Transform Mode: %s", controller.transform_mode)
            return True
        if key == optional_arcade.arcade.key.E:
            controller.transform_mode = TRANSFORM_MODE_ROTATE
            logger.info("[Editor] Transform Mode: %s", controller.transform_mode)
            return True
        if key == optional_arcade.arcade.key.Q:
            controller.transform_mode = TRANSFORM_MODE_SCALE
            logger.info("[Editor] Transform Mode: %s", controller.transform_mode)
            return True

    if controller.selected_entity and (modifiers & optional_arcade.arcade.key.MOD_SHIFT) and not (modifiers & optional_arcade.arcade.key.MOD_CTRL):
        if key == optional_arcade.arcade.key.A:
            return controller._apply_prefab_shapes(only_missing=True)
        if key == optional_arcade.arcade.key.R and not controller.hierarchy_active:
            return controller._apply_prefab_shapes(only_missing=False)
        if key == optional_arcade.arcade.key.P:
            return controller._promote_prefab_shapes()

    if key == optional_arcade.arcade.key.L and not modifiers:
        return run_editor_action("editor.light_tool.toggle", controller, controller.window)

    if controller.lights_tool_active and not controller.palette_active:
        if key == optional_arcade.arcade.key.P and not modifiers:
            return controller.capture_lighting_preset("custom_1")
        if key == optional_arcade.arcade.key.P and (modifiers & optional_arcade.arcade.key.MOD_SHIFT):
            return controller.capture_lighting_preset("custom_2")

    if not controller.palette_active and not modifiers:
        if optional_arcade.arcade.key.KEY_1 <= key <= optional_arcade.arcade.key.KEY_4:
            return controller.apply_lighting_preset_hotkey(key - optional_arcade.arcade.key.KEY_1)
        if key == optional_arcade.arcade.key.KEY_5:
            return controller.apply_custom_lighting_preset("custom_1")
        if key == optional_arcade.arcade.key.KEY_6:
            return controller.apply_custom_lighting_preset("custom_2")

    if controller.lights_tool_active and controller.lights_selection is not None:
        if controller._handle_lights_key_input(key, modifiers):
            return True

    if controller.occluder_tool_active:
        if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
            return controller._commit_occluder_polygon()
        if key in (optional_arcade.arcade.key.BACKSPACE, optional_arcade.arcade.key.DELETE):
            return controller._handle_occluder_key_input(key)
        if key == optional_arcade.arcade.key.I:
            return controller._handle_occluder_key_input(key)
        if key == optional_arcade.arcade.key.ESCAPE:
            controller._toggle_occluder_mode(False)
            return True

    if key == optional_arcade.arcade.key.D and not modifiers and controller._entity_has_dialogue(controller.selected_entity):
        controller.toggle_dialogue_panel()
        return True

    if controller.dialogue_panel_active:
        if controller._handle_dialogue_input(key, modifiers):
            return True

    if key == optional_arcade.arcade.key.A and not modifiers and controller._entity_has_animator(controller.selected_entity):
        controller.toggle_animation_panel()
        return True

    if controller.animation_active:
        if controller._handle_animation_input(key, modifiers):
            return True

    if key == optional_arcade.arcade.key.G and not modifiers and controller._tilemap_available():
        controller.toggle_tile_panel()
        return True

    if controller.tile_panel_active:
        if controller._handle_tile_input(key, modifiers):
            return True

    # Hierarchy rename shortcut (Shift+R)
    if (
        key == optional_arcade.arcade.key.R
        and controller.hierarchy_active
        and (modifiers & optional_arcade.arcade.key.MOD_SHIFT)
        and not (modifiers & optional_arcade.arcade.key.MOD_CTRL)
    ):
        if controller._begin_hierarchy_rename():
            return True

    # Toggle Palette
    if key == optional_arcade.arcade.key.P:
        return run_editor_action("editor.prefab_palette.toggle", controller, controller.window)

    # Palette filter Tab-to-insert should win over global Tab inspector toggle.
    if controller.palette_active and controller.palette_filter_active and key == optional_arcade.arcade.key.TAB:
        return controller._handle_palette_input(key, modifiers)

    # Cycle Zone Target (Ctrl+R)
    if key == optional_arcade.arcade.key.R and (modifiers & optional_arcade.arcade.key.MOD_CTRL):
        if controller.tool_mode == "ZONE":
            return controller._cycle_zone_behaviour()
        return False

    # Toggle between trigger/hitbox when both exist (T)
    if key == optional_arcade.arcade.key.T and not modifiers:
        if controller.tool_mode == "ZONE" and controller._toggle_zone_edit_target():
            return True

    # Cycle Tool Mode (plain R)
    if key == optional_arcade.arcade.key.R and not (modifiers & (optional_arcade.arcade.key.MOD_SHIFT | optional_arcade.arcade.key.MOD_CTRL)):
        controller._cycle_tool_mode()
        return True

    # Toggle Inspector Focus
    if key == optional_arcade.arcade.key.TAB:
        if controller.selected_entity:
            controller.inspector_active = not controller.inspector_active
            if controller.inspector_active:
                controller.palette_active = False  # Mutually exclusive
                controller.hierarchy_active = False
                controller._refresh_inspector_items()
        return True

    # Toggle Hierarchy
    if key == optional_arcade.arcade.key.H:
        controller.toggle_hierarchy()
        return True

    # Copy/Paste (Ctrl+C / Ctrl+V) - skip if in text input mode
    if not _is_text_input_active(controller):
        if key == optional_arcade.arcade.key.C and (modifiers & optional_arcade.arcade.key.MOD_CTRL):
            copier = getattr(controller, "copy_selected_entity_to_clipboard", None)
            if callable(copier):
                copier()
            return True

        if key == optional_arcade.arcade.key.V and (modifiers & optional_arcade.arcade.key.MOD_CTRL):
            paster = getattr(controller, "paste_entity_from_clipboard", None)
            if callable(paster):
                paster()
            return True

    if controller.palette_active:
        return controller._handle_palette_input(key, modifiers)

    if controller.hierarchy_active:
        return controller._handle_hierarchy_input(key, modifiers)

    if controller.inspector_active and controller.selected_entity:
        return controller._handle_inspector_input(key, modifiers)

    # Tool-specific input
    if controller.tool_mode == "PATH":
        if controller._handle_path_input(key, modifiers):
            return True
    elif controller.tool_mode == "ZONE":
        if controller._handle_zone_input(key, modifiers):
            return True

    # Default movement (fallback)
    return controller._handle_movement_input(key, modifiers)


def handle_mouse_drag(
    controller: EditorController,
    x: float,
    y: float,
    dx: float,
    dy: float,
    buttons: int,
    modifiers: int,
) -> bool:
    if not controller.active:
        return False

    wx, wy = controller.window.screen_to_world(x, y)

    # Alt-drag duplicate - handle before other drags
    if getattr(controller, "_alt_dup_active", False):
        controller.update_alt_drag_duplicate(wx, wy)
        return True

    # Marquee selection drag - handle before other drags
    if getattr(controller, "_marquee_active", False):
        controller.update_marquee(wx, wy)
        return True

    # Dock splitter drag has priority over all other drags
    dock_drag_active = getattr(controller, "_dock_drag_active", None)
    if dock_drag_active is not None:
        update_drag = getattr(controller, "update_dock_drag", None)
        if callable(update_drag):
            update_drag(x, controller.window.width)
        return True

    wx, wy = controller.window.screen_to_world(x, y)

    # Light dragging
    if controller.lights_tool_active and controller.lights_dragging and controller.lights_selection is not None:
        lights = controller._get_scene_lights()
        if 0 <= controller.lights_selection < len(lights):
            sx, sy = controller._snap_world_point(wx, wy)
            lights[controller.lights_selection]["x"] = sx
            lights[controller.lights_selection]["y"] = sy
            mark_dirty = getattr(controller, "_mark_dirty", None)
            if callable(mark_dirty):
                mark_dirty()
            else:
                controller.scene_dirty = True
            controller._sync_lighting_runtime()
        return True

    if controller.occluder_tool_active and controller.occluder_dragging and (buttons & optional_arcade.arcade.MOUSE_BUTTON_LEFT):
        return controller._update_occluder_point(wx, wy, push_command=False)

    if (
        controller.shape_edit_mode
        and controller.shape_drag_index >= 0
        and (buttons & optional_arcade.arcade.MOUSE_BUTTON_LEFT)
    ):
        return controller._update_shape_point(wx, wy, modifiers)

    # Rotate dragging (multi-select)
    if getattr(controller, "_rotate_drag_active", False) and controller.selected_entity and controller.tool_mode == "MOVE":
        return _handle_rotate_drag(controller, wx, wy, modifiers)

    # Scale dragging (multi-select)
    if getattr(controller, "_scale_drag_active", False) and controller.selected_entity and controller.tool_mode == "MOVE":
        return _handle_scale_drag(controller, wx, wy, modifiers)

    # Entity dragging (multi-select aware)
    if controller.entity_dragging and controller.selected_entity and controller.tool_mode == "MOVE":
        from ..editor.editor_transform_ops import apply_snap_to_xy, compute_dragged_xy  # noqa: PLC0415
        from .state import get_sprite_for_entity_id  # noqa: PLC0415

        # Apply snapping using controller settings (anchor to primary/dragged entity)
        snap_enabled = getattr(controller, "snap_enabled", True)
        snap_mode = getattr(controller, "snap_mode", "grid16")
        tile_size = int(getattr(controller, "grid_size", 16))

        # Get primary entity start position for delta calculation
        primary_id = getattr(controller, "_primary_entity_id", None)
        drag_starts = getattr(controller, "_multiselect_drag_starts", {})
        primary_start = drag_starts.get(primary_id) if primary_id else controller.entity_drag_start_pos

        if primary_start:
            # Compute raw dragged position for primary
            raw_primary_xy = compute_dragged_xy(primary_start, controller.entity_drag_start_pos or primary_start, (wx, wy))
            # Snap primary position
            snapped_primary = apply_snap_to_xy(raw_primary_xy, snap_enabled, snap_mode, tile_size)
            # Compute delta from snapped primary position
            delta = (snapped_primary[0] - primary_start[0], snapped_primary[1] - primary_start[1])

            # Store preview state for gizmo overlay
            controller._move_preview_delta_xy = delta
            controller._transform_snap_active = snap_enabled

            # Apply delta to all selected entities
            selected_ids = getattr(controller, "_selected_entity_ids", [])
            for eid in selected_ids:
                start_pos = drag_starts.get(eid)
                if start_pos:
                    sprite = get_sprite_for_entity_id(controller, eid)
                    if sprite:
                        sprite.center_x = start_pos[0] + delta[0]
                        sprite.center_y = start_pos[1] + delta[1]
        else:
            # Fallback to single entity drag
            snapped = apply_snap_to_xy((wx, wy), snap_enabled, snap_mode, tile_size)
            controller.selected_entity.center_x = snapped[0]
            controller.selected_entity.center_y = snapped[1]
            # Store preview for single entity
            start_pos = getattr(controller, "entity_drag_start_pos", None)
            if start_pos:
                controller._move_preview_delta_xy = (snapped[0] - start_pos[0], snapped[1] - start_pos[1])
                controller._transform_snap_active = snap_enabled

        # Don't mark dirty during drag - only on release
        return True

    return False


def handle_mouse_release(controller: EditorController, x: float, y: float, button: int, modifiers: int) -> bool:
    if not controller.active:
        return False

    # Alt-drag duplicate release - handle before other releases
    if getattr(controller, "_alt_dup_active", False) and button == optional_arcade.arcade.MOUSE_BUTTON_LEFT:
        controller.end_alt_drag_duplicate()
        return True

    # Marquee selection release - handle before other releases
    if getattr(controller, "_marquee_active", False) and button == optional_arcade.arcade.MOUSE_BUTTON_LEFT:
        controller.end_marquee()
        return True

    # Dock splitter drag release has priority
    dock_drag_active = getattr(controller, "_dock_drag_active", None)
    if dock_drag_active is not None and button == optional_arcade.arcade.MOUSE_BUTTON_LEFT:
        end_drag = getattr(controller, "end_dock_drag", None)
        if callable(end_drag):
            end_drag()
        return True

    # Light dragging release
    if controller.lights_tool_active and controller.lights_dragging and controller.lights_selection is not None:
        controller.lights_dragging = False
        lights = controller._get_scene_lights()
        if not (0 <= controller.lights_selection < len(lights)):
            return False
        if controller.lights_original_pos is None:
            return False
        light = lights[controller.lights_selection]
        new_pos = (float(light.get("x", 0.0)), float(light.get("y", 0.0)))
        if new_pos != controller.lights_original_pos:
            controller._push_command(
                {
                    "type": "MoveLight",
                    "index": controller.lights_selection,
                    "from": controller.lights_original_pos,
                    "to": new_pos,
                }
            )
        controller.lights_original_pos = None
        controller._sync_lighting_runtime()
        return True

    if controller.occluder_tool_active and controller.occluder_dragging and button == optional_arcade.arcade.MOUSE_BUTTON_LEFT:
        controller.occluder_dragging = False
        if controller.occluder_selection is not None and controller.occluder_vertex_selection is not None:
            start = controller.occluder_drag_origin
            end = controller._get_occluder_point(controller.occluder_selection, controller.occluder_vertex_selection)
            if start is not None and end is not None and (start[0] != end[0] or start[1] != end[1]):
                occ_idx = controller.occluder_selection
                pt_idx = controller.occluder_vertex_selection
                cmd = controller._build_move_occluder_cmd(occ_idx, pt_idx, start, end)
                if cmd is not None:
                    controller._push_command({"type": "EditOccluder", "cmd": {"kind": cmd.kind, "payload": cmd.payload}})
                    controller._sync_occluders_runtime()
        controller.occluder_drag_origin = None
        return True

    # Rotate drag release
    if getattr(controller, "_rotate_drag_active", False) and controller.selected_entity:
        return _finish_rotate_drag(controller)

    # Scale drag release
    if getattr(controller, "_scale_drag_active", False) and controller.selected_entity:
        return _finish_scale_drag(controller)

    # Entity dragging release (multi-select aware)
    if controller.entity_dragging and controller.selected_entity:
        controller.entity_dragging = False
        drag_starts = getattr(controller, "_multiselect_drag_starts", {})
        selected_ids = getattr(controller, "_selected_entity_ids", [])

        if drag_starts and len(selected_ids) > 1:
            # Multi-entity move: create group command
            from ..editor.editor_transform_ops import (  # noqa: PLC0415
                MoveEntityCommand,
                MoveEntitiesCommand,
            )
            from .state import get_sprite_for_entity_id  # noqa: PLC0415

            moves = []
            any_moved = False
            for eid in selected_ids:
                start_pos = drag_starts.get(eid)
                if start_pos:
                    sprite = get_sprite_for_entity_id(controller, eid)
                    if sprite:
                        end_pos = (sprite.center_x, sprite.center_y)
                        if start_pos != end_pos:
                            any_moved = True
                        moves.append(MoveEntityCommand(entity_id=eid, start_xy=start_pos, end_xy=end_pos))

            if any_moved and moves:
                group_cmd = MoveEntitiesCommand(moves=tuple(moves))
                controller._push_command(group_cmd.to_dict())
                logger.info("[Editor] Moved %d entities", len(moves))
        elif controller.entity_drag_start_pos:
            # Single entity move
            from ..editor.editor_transform_ops import create_move_command_from_drag  # noqa: PLC0415

            end_xy = (controller.selected_entity.center_x, controller.selected_entity.center_y)
            entity_id = controller._get_display_name_for_sprite(controller.selected_entity)
            move_cmd = create_move_command_from_drag(entity_id, controller.entity_drag_start_pos, end_xy)
            if move_cmd is not None:
                controller._push_command(move_cmd.to_dict())
                logger.info("[Editor] Moved entity %s to %s", entity_id, end_xy)

        controller.entity_drag_start_pos = None
        controller._multiselect_drag_starts = {}
        # Clear preview state for gizmo overlay
        controller._move_preview_delta_xy = None
        controller._transform_snap_active = False
        return True

    if controller.shape_edit_mode and controller.shape_drag_index >= 0 and button == optional_arcade.arcade.MOUSE_BUTTON_LEFT:
        controller.shape_drag_index = -1
        return True

    return False


def handle_text_input(controller: EditorController, text: str) -> None:
    if not controller.active:
        return

    if getattr(controller, "confirm_open", False):
        return

    # Project Explorer inline rename text input
    project_ctrl = getattr(controller, "project_explorer", None)
    if project_ctrl is not None and getattr(project_ctrl, "inline_rename_active", False):
        handler = getattr(project_ctrl, "handle_rename_text_input", None)
        if callable(handler) and handler(text):
            return

    is_search_focused = getattr(controller, "is_search_focused", None)
    append_search = getattr(controller, "append_search_text", None)
    if callable(is_search_focused) and is_search_focused():
        if callable(append_search):
            append_search(text)
        return

    if getattr(controller, "_find_everything_open", False):
        appender = getattr(controller, "append_find_query_text", None)
        if callable(appender):
            appender(text)
        return

    if getattr(controller, "scene_browser_active", False):
        handler = getattr(controller, "_handle_scene_browser_text_input", None)
        if callable(handler) and handler(text):
            return

    if getattr(controller, "scene_switcher_active", False):
        handler = getattr(controller, "_handle_scene_switcher_text_input", None)
        if callable(handler) and handler(text):
            return

    if controller.command_palette_active:
        if text and text.isprintable():
            controller.command_palette_query += text
            controller.command_palette_index = 0
        return

    if controller.entity_panels_active:
        handler = getattr(controller, "_handle_entity_panels_text_input", None)
        if callable(handler) and handler(text):
            return

    # Component Inspector text input (when in text edit mode)
    if getattr(controller, "_inspector_text_edit_active", False):
        inspector_text_handler = getattr(controller, "_handle_inspector_text_input", None)
        if callable(inspector_text_handler) and inspector_text_handler(text):
            return

    if controller.dialogue_panel_active and controller.dialogue_editing:
        if text and text.isprintable():
            controller.dialogue_edit_buffer += text
        return

    if controller.animation_active and controller.animation_editing:
        if text and text.isprintable():
            controller.animation_edit_buffer += text
        return

    if controller.palette_active and controller.palette_filter_active:
        if text.isprintable():
            controller.palette_filter += text
            controller._refresh_palette_list()
            prewarm = getattr(controller, "_prewarm_visible_palette_thumbs", None)
            if callable(prewarm):
                prewarm()
        return

    if not controller.hierarchy_active:
        return

    if controller.hierarchy_rename_active:
        if text not in ("\r", "\n") and text.isprintable():
            controller.hierarchy_rename_buffer += text
        return

    if controller.hierarchy_filter_active:
        # Filter out control chars if any leak through
        if text.isprintable():
            controller.hierarchy_filter += text
            controller._refresh_hierarchy_list()


# ------------------------------------------------------------------------------
# Dock Splitter Helpers
# ------------------------------------------------------------------------------


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

    # Get effective dock widths for layout
    getter = getattr(controller, "get_effective_dock_widths", None)
    if callable(getter):
        left_w, right_w = getter(controller.window.width)
    else:
        left_w = getattr(controller, "_dock_left_w", 320)
        right_w = getattr(controller, "_dock_right_w", 320)

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
        toggle_fn = getattr(controller, "toggle_left_dock", None)
        if callable(toggle_fn):
            toggle_fn()
        return True
    elif hit == "toggle_right":
        toggle_fn = getattr(controller, "toggle_right_dock", None)
        if callable(toggle_fn):
            toggle_fn()
        return True
    elif hit == "toggle_max":
        toggle_fn = getattr(controller, "toggle_viewport_maximized", None)
        if callable(toggle_fn):
            toggle_fn()
        return True

    return None


# ------------------------------------------------------------------------------
# Splitter Drag Helpers
# ------------------------------------------------------------------------------


def _handle_splitter_click(controller: EditorController, x: float, y: float) -> bool | None:
    """Handle splitter click to begin dock resize. Returns True if consumed, None to pass through."""
    from ..editor.editor_shell_layout import (
        compute_editor_shell_layout,
        hit_test_splitter,
    )

    # Don't allow splitter dragging when viewport is maximized
    if getattr(controller, "_viewport_maximized", False):
        return None

    left_w = getattr(controller, "_dock_left_w", 320)
    right_w = getattr(controller, "_dock_right_w", 320)

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
    if hit == "left" and getattr(controller, "_dock_left_collapsed", False):
        return None
    if hit == "right" and getattr(controller, "_dock_right_collapsed", False):
        return None

    begin_drag = getattr(controller, "begin_dock_drag", None)
    if callable(begin_drag):
        begin_drag(hit, x)
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

    # Don't allow dock tab clicks when viewport is maximized
    if getattr(controller, "_viewport_maximized", False):
        return None

    # Get effective dock widths
    getter = getattr(controller, "get_effective_dock_widths", None)
    if callable(getter):
        left_w, right_w = getter(controller.window.width)
    else:
        left_w = getattr(controller, "_dock_left_w", 320)
        right_w = getattr(controller, "_dock_right_w", 320)

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
    set_dock_tab = getattr(controller, "set_dock_tab", None)
    if callable(set_dock_tab):
        set_dock_tab(dock, tab_name)
        return True

    return None


# ------------------------------------------------------------------------------
# Menu Bar Helpers
# ------------------------------------------------------------------------------


def _handle_menu_bar_click(controller: EditorController, x: float, y: float) -> bool | None:
    """Handle menu bar click. Returns True if consumed, False to close menu, None to pass through."""
    from ..editor.menu_bar_model import (
        build_menu_groups,
        compute_menu_bar_layout,
        hit_test_menu_title,
        hit_test_menu_item,
        hit_test_menu_bar,
        get_dropdown_bounds,
    )

    active_menu = getattr(controller, "_menu_active", None)
    menu_groups = build_menu_groups(controller, controller.window)
    layout = compute_menu_bar_layout(
        controller.window.width,
        controller.window.height,
        menu_groups,
        active_menu,
    )

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
    active_menu = getattr(controller, "_menu_active", None)
    if not active_menu:
        return False

    from ..editor.menu_bar_model import (
        build_menu_groups,
        compute_menu_bar_layout,
        hit_test_menu_title,
        hit_test_menu_item,
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


def _execute_menu_item(controller: EditorController, item_id: str) -> None:
    """Execute a menu item action."""
    from engine.editor.editor_actions import run_editor_action

    try:
        run_editor_action(item_id, controller, controller.window)
    except Exception as exc:  # noqa: BLE001
        logger.error("[Editor] Menu action failed: %s", exc)


def handle_menu_bar_key(controller: EditorController, key: int, modifiers: int) -> bool:
    """Handle key press for menu bar. Returns True if consumed."""
    active_menu = getattr(controller, "_menu_active", None)
    if not active_menu:
        return False

    if key == optional_arcade.arcade.key.ESCAPE:
        controller._menu_active = None
        controller._menu_hover_item_id = None
        return True

    return False

# ------------------------------------------------------------------------------
# Context Menu Handlers
# ------------------------------------------------------------------------------


def _handle_context_menu_click(controller: EditorController, x: float, y: float) -> bool | None:
    """Handle context menu click. Returns True if consumed, False to close, None to pass through."""
    from ..editor.context_menu_model import (
        build_context_menu_items,
        compute_context_menu_layout,
        hit_test_context_menu,
        hit_test_context_menu_bounds,
    )

    context_open = getattr(controller, "_context_menu_open", False)

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
    controller._context_menu_open = True
    controller._context_menu_x = x
    controller._context_menu_y = y
    controller._context_menu_hover_id = None


def _close_context_menu(controller: EditorController) -> None:
    """Close the context menu."""
    controller._context_menu_open = False
    controller._context_menu_hover_id = None


def handle_context_menu_motion(controller: EditorController, x: float, y: float) -> bool:
    """Handle mouse motion for context menu hover effects.

    Returns True if context menu is open and motion was handled.
    """
    if not getattr(controller, "_context_menu_open", False):
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


def handle_context_menu_key(controller: EditorController, key: int, modifiers: int) -> bool:
    """Handle key press for context menu. Returns True if consumed."""
    if not getattr(controller, "_context_menu_open", False):
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


def _handle_rotate_drag(controller: EditorController, wx: float, wy: float, modifiers: int) -> bool:
    """Handle mouse drag during rotation transform."""
    from ..editor.editor_rotate_ops import (  # noqa: PLC0415
        apply_rotate_entities,
        compute_angle_deg,
        compute_rotation_delta_deg,
        snap_rot_deg,
    )
    from .state import get_sprite_for_entity_id  # noqa: PLC0415

    pivot = getattr(controller, "_transform_drag_pivot", None)
    mouse_start = getattr(controller, "_transform_drag_mouse_start", None)
    start_rots = getattr(controller, "_transform_drag_start_rots", {})
    selected_ids = getattr(controller, "_selected_entity_ids", [])

    if pivot is None or not start_rots:
        return False

    # Capture first drag position as mouse_start if not set
    if mouse_start is None or mouse_start == pivot:
        controller._transform_drag_mouse_start = (wx, wy)
        return True  # First frame, don't apply yet

    # Compute rotation delta from pivot
    start_angle = compute_angle_deg(pivot[0], pivot[1], mouse_start[0], mouse_start[1])
    current_angle = compute_angle_deg(pivot[0], pivot[1], wx, wy)
    delta = current_angle - start_angle
    # Wrap to [-180, 180]
    while delta > 180.0:
        delta -= 360.0
    while delta < -180.0:
        delta += 360.0

    # Apply snapping if enabled (Shift = 15 degree increments)
    snap_enabled = bool(modifiers & optional_arcade.arcade.key.MOD_SHIFT)
    if snap_enabled:
        delta = snap_rot_deg(delta, 15.0)

    # Store preview state for gizmo overlay
    controller._rotate_preview_delta_deg = delta
    controller._transform_snap_active = snap_enabled

    # Apply rotation to all selected entities
    for eid in selected_ids:
        sprite = get_sprite_for_entity_id(controller, eid)
        if sprite and eid in start_rots:
            sprite.angle = start_rots[eid] + delta

    return True


def _handle_scale_drag(controller: EditorController, wx: float, wy: float, modifiers: int) -> bool:
    """Handle mouse drag during scale transform."""
    from ..editor.editor_scale_ops import (  # noqa: PLC0415
        clamp_scale,
        compute_scale_factor,
        snap_scale_factor,
    )
    from .state import get_sprite_for_entity_id  # noqa: PLC0415

    pivot = getattr(controller, "_transform_drag_pivot", None)
    mouse_start = getattr(controller, "_transform_drag_mouse_start", None)
    start_scales = getattr(controller, "_transform_drag_start_scales", {})
    selected_ids = getattr(controller, "_selected_entity_ids", [])

    if pivot is None or not start_scales:
        return False

    # Capture first drag position as mouse_start if not set
    if mouse_start is None or mouse_start == pivot:
        controller._transform_drag_mouse_start = (wx, wy)
        return True  # First frame, don't apply yet

    # Compute scale factor from pivot distance
    factor = compute_scale_factor(pivot, mouse_start, (wx, wy))

    # Apply snapping if enabled (Shift = 0.1 increments)
    snap_enabled = modifiers & optional_arcade.arcade.key.MOD_SHIFT
    if snap_enabled:
        factor = snap_scale_factor(factor, 0.1)

    # Store preview state for gizmo overlay
    controller._scale_preview_factor = factor
    controller._transform_snap_active = bool(snap_enabled)

    # Apply scale to all selected entities
    for eid in selected_ids:
        sprite = get_sprite_for_entity_id(controller, eid)
        if sprite and eid in start_scales:
            new_scale = clamp_scale(start_scales[eid] * factor)
            sprite.scale = new_scale

    return True


def _finish_rotate_drag(controller: EditorController) -> bool:
    """Finish rotation drag and push command to undo stack."""
    from ..editor.editor_rotate_ops import (  # noqa: PLC0415
        RotateEntityCommand,
        RotateEntitiesCommand,
    )
    from .state import get_sprite_for_entity_id  # noqa: PLC0415

    start_rots = getattr(controller, "_transform_drag_start_rots", {})
    selected_ids = getattr(controller, "_selected_entity_ids", [])

    rotates = []
    any_changed = False
    for eid in selected_ids:
        start_rot = start_rots.get(eid)
        if start_rot is None:
            continue
        sprite = get_sprite_for_entity_id(controller, eid)
        if sprite:
            end_rot = getattr(sprite, "angle", 0.0)
            if abs(end_rot - start_rot) > 0.001:
                any_changed = True
            rotates.append(RotateEntityCommand(entity_id=eid, start_rot_deg=start_rot, end_rot_deg=end_rot))

    if any_changed and rotates:
        group_cmd = RotateEntitiesCommand(rotates=tuple(rotates))
        controller._push_command(group_cmd.to_dict())
        logger.info("[Editor] Rotated %d entities", len(rotates))

    # Reset drag state
    controller._rotate_drag_active = False
    controller._transform_drag_pivot = None
    controller._transform_drag_mouse_start = None
    controller._transform_drag_start_rots = {}
    # Clear preview state for gizmo overlay
    controller._rotate_preview_delta_deg = None
    controller._transform_snap_active = False

    return True


def _finish_scale_drag(controller: EditorController) -> bool:
    """Finish scale drag and push command to undo stack."""
    from ..editor.editor_scale_ops import (  # noqa: PLC0415
        ScaleEntityCommand,
        ScaleEntitiesCommand,
    )
    from .state import get_sprite_for_entity_id  # noqa: PLC0415

    start_scales = getattr(controller, "_transform_drag_start_scales", {})
    selected_ids = getattr(controller, "_selected_entity_ids", [])

    scales = []
    any_changed = False
    for eid in selected_ids:
        start_scale = start_scales.get(eid)
        if start_scale is None:
            continue
        sprite = get_sprite_for_entity_id(controller, eid)
        if sprite:
            end_scale = getattr(sprite, "scale", 1.0)
            if isinstance(end_scale, tuple):
                end_scale = end_scale[0] if end_scale else 1.0
            if abs(end_scale - start_scale) > 0.001:
                any_changed = True
            scales.append(ScaleEntityCommand(entity_id=eid, start_scale=start_scale, end_scale=float(end_scale)))

    if any_changed and scales:
        group_cmd = ScaleEntitiesCommand(scales=tuple(scales))
        controller._push_command(group_cmd.to_dict())
        logger.info("[Editor] Scaled %d entities", len(scales))

    # Reset drag state
    controller._scale_drag_active = False
    controller._transform_drag_pivot = None
    controller._transform_drag_mouse_start = None
    controller._transform_drag_start_scales = {}
    # Clear preview state for gizmo overlay
    controller._scale_preview_factor = None
    controller._transform_snap_active = False

    return True
