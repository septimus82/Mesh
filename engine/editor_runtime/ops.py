from __future__ import annotations

from typing import Any

from ..logging_tools import get_logger
from .. import json_io

logger = get_logger(__name__)


def nudge_selected(controller: Any, dx: float, dy: float) -> None:
    if not controller.active or not controller.selected_entity:
        return

    old_x = controller.selected_entity.center_x
    old_y = controller.selected_entity.center_y
    new_x = old_x + dx
    new_y = old_y + dy
    entity_name = getattr(controller.selected_entity, "mesh_name", "")

    # Use scene controller to apply mutation so it syncs with entity data
    controller.window.scene_controller._apply_entity_mutation(
        controller.selected_entity,
        x=new_x,
        y=new_y,
    )

    controller._push_command(
        {
            "type": "MoveEntity",
            "entity_name": entity_name,
            "before": {"x": old_x, "y": old_y},
            "after": {"x": new_x, "y": new_y},
        }
    )


def save_current_scene(controller: Any) -> None:
    if not controller.active:
        return

    path = controller.window.scene_controller.current_scene_path
    if not path:
        logger.info("[Editor] Error: No scene path to save to.")
        return

    try:
        snapshot = controller.window.scene_controller.build_scene_snapshot()
        json_io.write_json_atomic(path, snapshot)
        logger.info("[Editor] Scene saved to '%s'", path)
        mark_clean = getattr(controller, "_mark_clean", None)
        if callable(mark_clean):
            mark_clean()
        else:
            controller.scene_dirty = False
        try:
            from ..i18n import tr  # noqa: PLC0415

            hud = getattr(controller.window, "player_hud", None)
            enqueue = getattr(hud, "enqueue_toast", None) if hud is not None else None
            if callable(enqueue):
                enqueue(tr("UI_SCENE_SAVED"), seconds=2.0)
        except Exception:  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001
        logger.info("[Editor] Error saving scene: %s", exc)


def toggle_palette(controller: Any) -> None:
    if not controller.active:
        return
    controller.palette_active = not controller.palette_active
    if controller.palette_active:
        controller.inspector_active = False
        controller.hierarchy_active = False
        controller.palette_filter_active = False
        refresh = getattr(controller, "_refresh_palette_list", None)
        if callable(refresh):
            refresh()
        logger.info("[Editor] Palette OPEN")
    else:
        controller.palette_filter_active = False
        logger.info("[Editor] Palette CLOSED")


def move_palette_selection(controller: Any, delta: int) -> None:
    if not controller.palette_active:
        return
    items = controller.prefab_palette
    getter = getattr(controller, "_get_palette_items", None)
    if callable(getter):
        items = getter()
    count = len(items)
    if count == 0:
        return
    controller.palette_index = (controller.palette_index + delta) % count


def select_palette_index(controller: Any, index: int) -> None:
    if not controller.palette_active:
        return
    items = controller.prefab_palette
    getter = getattr(controller, "_get_palette_items", None)
    if callable(getter):
        items = getter()
    if 0 <= index < len(items):
        controller.palette_index = index


def toggle_lights_tool(controller: Any) -> None:
    if not controller.active:
        return
    controller._toggle_lights_mode(not controller.lights_tool_active)


def toggle_occluder_tool(controller: Any) -> None:
    if not controller.active:
        return
    controller._toggle_occluder_mode(not controller.occluder_tool_active)


def place_entity_at_mouse(controller: Any, x: float, y: float) -> None:
    if not controller.active or not controller.palette_active:
        return

    items = controller.prefab_palette
    getter = getattr(controller, "_get_palette_items", None)
    if callable(getter):
        items = getter()
    if not (0 <= controller.palette_index < len(items)):
        return

    prefab = items[controller.palette_index]
    world_x, world_y = controller.window.screen_to_world(x, y)

    # Snap to grid
    grid = controller.grid_size
    snap_x = round(world_x / grid) * grid
    snap_y = round(world_y / grid) * grid

    entity_def = dict(prefab["entity"])
    entity_def["x"] = snap_x
    entity_def["y"] = snap_y

    # Ensure unique name
    base_name = entity_def.get("name", "Entity")
    existing_count = len(list(controller.window.scene_controller.all_sprites))
    entity_def["name"] = f"{base_name}_{existing_count + 1}"

    sprite = controller._create_entity_internal(entity_def)
    if sprite:
        logger.info("[Editor] Placed %s at (%s, %s)", prefab["display_name"], snap_x, snap_y)
        controller._push_command(
            {
                "type": "AddEntity",
                "entity_name": entity_def["name"],
                "data": entity_def,
            }
        )


def duplicate_selected(controller: Any) -> None:
    if not controller.active or not controller.selected_entity:
        return

    sprite = controller.selected_entity
    entity_data = getattr(sprite, "mesh_entity_data", None)
    if not isinstance(entity_data, dict):
        logger.info("[Editor] Cannot duplicate: missing entity data")
        return

    new_data = dict(entity_data)

    # Offset position
    new_data["x"] = float(new_data.get("x", 0)) + controller.grid_size
    new_data["y"] = float(new_data.get("y", 0)) - controller.grid_size

    # New name
    base_name = new_data.get("name", "Entity")
    new_data["name"] = f"{base_name}_copy"

    # Create
    new_sprite = controller._create_entity_internal(new_data)
    if new_sprite:
        controller.selected_entity = new_sprite  # Select the new one
        controller._reset_zone_selection_state()
        controller._sync_zone_selection_state(controller.selected_entity)
        logger.info("[Editor] Duplicated entity to %s", new_data["name"])
        controller._push_command(
            {
                "type": "AddEntity",
                "entity_name": new_data["name"],
                "data": new_data,
            }
        )


def delete_selected(controller: Any) -> None:
    if not controller.active or not controller.selected_entity:
        return

    sprite = controller.selected_entity
    name = getattr(sprite, "mesh_name", "<unnamed>")
    entity_data = getattr(sprite, "mesh_entity_data", {})

    controller._delete_entity_internal(sprite)
    logger.info("[Editor] Deleted entity: %s", name)

    controller._push_command(
        {
            "type": "DeleteEntity",
            "entity_name": name,
            "data": entity_data,
        }
    )


def undo_last(controller: Any) -> None:
    if not controller.undo_stack:
        logger.info("[Editor] Nothing to undo.")
        return

    cmd = controller.undo_stack.pop()
    controller._revert_command(cmd)
    controller.redo_stack.append(cmd)
    logger.info("[Editor] Undid %s", cmd["type"])
    mark_dirty = getattr(controller, "_mark_dirty", None)
    if callable(mark_dirty):
        mark_dirty()
    else:
        controller.scene_dirty = True


def redo_last(controller: Any) -> None:
    if not controller.redo_stack:
        logger.info("[Editor] Nothing to redo.")
        return

    cmd = controller.redo_stack.pop()
    controller._apply_command(cmd)
    controller.undo_stack.append(cmd)
    logger.info("[Editor] Redid %s", cmd["type"])
    mark_dirty = getattr(controller, "_mark_dirty", None)
    if callable(mark_dirty):
        mark_dirty()
    else:
        controller.scene_dirty = True
