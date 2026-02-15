from __future__ import annotations

from typing import TYPE_CHECKING

import engine.optional_arcade as optional_arcade
from engine.editor.editor_dock_query import get_dock_drag_active

from ..logging_tools import get_logger
from .editor_input_transform_handlers import (
    handle_rotate_drag as _handle_rotate_drag,
    handle_scale_drag as _handle_scale_drag,
    finish_rotate_drag as _finish_rotate_drag,
    finish_scale_drag as _finish_scale_drag,
)

if TYPE_CHECKING:
    from engine.editor_controller import EditorModeController as EditorController

logger = get_logger(__name__)


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
    dock_drag_active = get_dock_drag_active(controller)
    if dock_drag_active is not None:
        dock_ctl = getattr(controller, "dock", None)
        update_drag = getattr(dock_ctl, "update_drag", None) if dock_ctl is not None else None
        if callable(update_drag):
            update_drag(controller, x, controller.window.width)
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
        return bool(controller._update_occluder_point(wx, wy, push_command=False))

    if (
        controller.shape_edit_mode
        and controller.shape_drag_index >= 0
        and (buttons & optional_arcade.arcade.MOUSE_BUTTON_LEFT)
    ):
        return controller.shape.update_shape_point(wx, wy, modifiers)

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
    dock_drag_active = get_dock_drag_active(controller)
    if dock_drag_active is not None and button == optional_arcade.arcade.MOUSE_BUTTON_LEFT:
        dock_ctl = getattr(controller, "dock", None)
        end_drag = getattr(dock_ctl, "end_drag", None) if dock_ctl is not None else None
        if callable(end_drag):
            end_drag(controller)
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
