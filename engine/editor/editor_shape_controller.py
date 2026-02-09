from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, cast

import engine.optional_arcade as optional_arcade

from engine.editor.state import TOOL_MODE_ZONE
from engine.behaviours.utils import (
    ZONE_TARGET_HITBOX,
    ZONE_TARGET_TRIGGER,
    describe_zone_behaviour,
    infer_zone_target_from_behaviour,
    is_hitbox_behaviour,
    is_trigger_behaviour,
)
from engine.logging_tools import get_logger

logger = get_logger(__name__)


class EditorShapeController:
    """Encapsulates patrol/path, zone, and shape editing logic."""

    def __init__(self, editor: Any) -> None:
        self._editor = editor

    def handle_path_input(self, key: int, modifiers: int) -> bool:
        if not self._editor.selected_entity:
            return False

        patrol = self.get_patrol_behaviour(self._editor.selected_entity)
        if not patrol:
            return False

        points = self.get_patrol_points(patrol)
        if not points:
            return False

        if self._editor.selected_waypoint_index < 0 or self._editor.selected_waypoint_index >= len(points):
            return False

        if key == optional_arcade.arcade.key.DELETE:
            self.remove_waypoint(patrol, self._editor.selected_waypoint_index)
            self._editor.selected_waypoint_index = -1
            return True

        grid = self._editor.grid_size
        dx, dy = 0.0, 0.0

        if key == optional_arcade.arcade.key.LEFT:
            dx = -grid
        elif key == optional_arcade.arcade.key.RIGHT:
            dx = grid
        elif key == optional_arcade.arcade.key.UP:
            dy = grid
        elif key == optional_arcade.arcade.key.DOWN:
            dy = -grid
        else:
            return False

        if modifiers & optional_arcade.arcade.key.MOD_SHIFT:
            dx *= 4
            dy *= 4

        self.move_waypoint(patrol, self._editor.selected_waypoint_index, dx, dy)
        return True

    def handle_zone_input(self, key: int, modifiers: int) -> bool:
        if not self._editor.selected_entity:
            return False

        zone = self.get_zone_behaviour(self._editor.selected_entity)
        if not zone:
            return False

        if not (modifiers & optional_arcade.arcade.key.MOD_SHIFT):
            return False

        dx, dy = 0.0, 0.0
        step = self._editor.grid_size

        if key == optional_arcade.arcade.key.LEFT:
            dx = -step
        elif key == optional_arcade.arcade.key.RIGHT:
            dx = step
        elif key == optional_arcade.arcade.key.UP:
            dy = step
        elif key == optional_arcade.arcade.key.DOWN:
            dy = -step
        else:
            return False

        self.resize_zone(zone, dx, dy)
        return True

    def shape_field_for_mode(self, mode: str) -> str:
        return "occluder_poly" if mode == "occluder" else "collision_poly"

    def begin_shape_edit(self, mode: str) -> bool:
        if not self._editor.selected_entity:
            return False
        key = self.shape_field_for_mode(mode)
        entity_data = getattr(self._editor.selected_entity, "mesh_entity_data", None)
        points: List[tuple[float, float]] = []
        if isinstance(entity_data, dict):
            raw = entity_data.get(key)
            if isinstance(raw, list):
                for entry in raw:
                    if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                        continue
                    try:
                        points.append((float(entry[0]), float(entry[1])))
                    except Exception:  # noqa: BLE001
                        continue
        self._editor.shape_edit_mode = mode
        self._editor.shape_edit_entity = self._editor.selected_entity
        self._editor.shape_edit_points = list(points)
        self._editor.shape_edit_original = list(points)
        self._editor.shape_drag_index = -1
        inspector = getattr(self._editor, "inspector", None)
        if inspector is not None:
            inspector.set_inspector_active(False)
        self._editor.palette_active = False
        self._editor.hierarchy_active = False
        return True

    def cancel_shape_edit(self) -> None:
        self._editor.shape_edit_mode = None
        self._editor.shape_edit_points = []
        self._editor.shape_edit_original = []
        self._editor.shape_edit_entity = None
        self._editor.shape_drag_index = -1

    def commit_shape_edit(self) -> bool:
        if not self._editor.shape_edit_mode or not self._editor.shape_edit_entity:
            return False
        entity = self._editor.shape_edit_entity
        key = self.shape_field_for_mode(self._editor.shape_edit_mode)
        before = list(self._editor.shape_edit_original)
        after = list(self._editor.shape_edit_points)

        self.set_entity_shape_points(entity, key, after)

        if before != after:
            name = getattr(entity, "mesh_name", "") or getattr(entity, "name", "")
            self._editor._push_command(
                {
                    "type": "EditShape",
                    "entity_name": name,
                    "field": key,
                    "before": [[float(x), float(y)] for x, y in before],
                    "after": [[float(x), float(y)] for x, y in after],
                }
            )
        self.cancel_shape_edit()
        return True

    def shape_pick_radius_world(self, radius_px: float) -> float:
        zoom = 1.0
        camera_controller = getattr(self._editor.window, "camera_controller", None)
        if camera_controller is not None:
            try:
                zoom = float(getattr(camera_controller, "zoom", 1.0))
            except Exception:  # noqa: BLE001
                zoom = 1.0
        if zoom <= 0.0:
            zoom = 1.0
        return float(radius_px) / zoom

    def nearest_shape_vertex_index(self, world_x: float, world_y: float, *, radius_px: float = 10.0) -> int:
        if not self._editor.shape_edit_mode or not self._editor.shape_edit_entity:
            return -1
        radius_world = self.shape_pick_radius_world(radius_px)
        radius_sq = radius_world * radius_world
        entity = self._editor.shape_edit_entity
        best_index = -1
        best_dist = radius_sq
        for idx, (px, py) in enumerate(self._editor.shape_edit_points):
            dx = float(world_x) - (float(entity.center_x) + float(px))
            dy = float(world_y) - (float(entity.center_y) + float(py))
            dist = dx * dx + dy * dy
            if dist <= best_dist:
                best_dist = dist
                best_index = idx
        return best_index

    def set_entity_shape_points(
        self,
        entity: optional_arcade.arcade.Sprite,
        key: str,
        points: List[tuple[float, float]],
    ) -> None:
        entity_data = self._editor.window.scene_controller._ensure_entity_data_dict(entity)
        if points:
            entity_data[key] = [[float(x), float(y)] for x, y in points]
        else:
            entity_data.pop(key, None)

        if key == "collision_poly":
            self._editor.window.scene_controller._apply_collision_poly(entity, entity_data.get(key))

    def coerce_shape_points(self, raw: Any) -> List[tuple[float, float]]:
        points: List[tuple[float, float]] = []
        if not isinstance(raw, list):
            return points
        for entry in raw:
            if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                continue
            try:
                points.append((float(entry[0]), float(entry[1])))
            except Exception:  # noqa: BLE001
                continue
        return points

    def shape_payload_for_undo(self, raw: Any) -> list[list[float]] | None:
        if not isinstance(raw, list):
            return None
        points: list[list[float]] = []
        for entry in raw:
            if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                continue
            try:
                points.append([float(entry[0]), float(entry[1])])
            except Exception:  # noqa: BLE001
                continue
        return points

    def apply_shape_payload(self, entity: optional_arcade.arcade.Sprite, field: str, payload: Any) -> None:
        points = self.coerce_shape_points(payload)
        self.set_entity_shape_points(entity, field, points)

    def add_shape_point(self, world_x: float, world_y: float) -> bool:
        if not self._editor.shape_edit_mode or not self._editor.shape_edit_entity:
            return False
        entity = self._editor.shape_edit_entity
        local_x = float(world_x) - float(entity.center_x)
        local_y = float(world_y) - float(entity.center_y)
        self._editor.shape_edit_points.append((local_x, local_y))
        return True

    def update_shape_point(self, world_x: float, world_y: float, modifiers: int) -> bool:
        if not self._editor.shape_edit_mode or not self._editor.shape_edit_entity:
            return False
        if self._editor.shape_drag_index < 0 or self._editor.shape_drag_index >= len(self._editor.shape_edit_points):
            return False
        entity = self._editor.shape_edit_entity
        local_x = float(world_x) - float(entity.center_x)
        local_y = float(world_y) - float(entity.center_y)
        if self._editor.shape_snap_enabled and self._editor.grid_size > 0:
            local_x = round(local_x / self._editor.grid_size) * self._editor.grid_size
            local_y = round(local_y / self._editor.grid_size) * self._editor.grid_size
        old_x, old_y = self._editor.shape_edit_points[self._editor.shape_drag_index]
        if modifiers & optional_arcade.arcade.key.MOD_SHIFT:
            dx = local_x - old_x
            dy = local_y - old_y
            if abs(dx) >= abs(dy):
                local_y = old_y
            else:
                local_x = old_x
        self._editor.shape_edit_points[self._editor.shape_drag_index] = (local_x, local_y)
        return True

    def remove_shape_point(self) -> bool:
        if not self._editor.shape_edit_mode:
            return False
        if self._editor.shape_edit_points:
            self._editor.shape_edit_points.pop()
            return True
        return False

    def toggle_shape_edit_mode(self, mode: str) -> bool:
        if self._editor.shape_edit_mode == mode:
            self.cancel_shape_edit()
            return True
        return self.begin_shape_edit(mode)

    def reset_zone_selection_state(self) -> None:
        self._editor.zone_behaviour_index = 0
        self._editor.zone_edit_target = ZONE_TARGET_TRIGGER

    def sync_zone_selection_state(self, entity: Optional[optional_arcade.arcade.Sprite]) -> None:
        if not entity:
            return

        behaviours = self.get_zone_behaviours(entity)
        if not behaviours:
            self._editor.zone_behaviour_index = 0
            return

        targeted = self.get_targeted_zone_behaviour(entity, behaviours)
        if targeted:
            return

        self._editor.zone_behaviour_index = 0
        self._editor.zone_edit_target = infer_zone_target_from_behaviour(behaviours[0])

    def split_zone_behaviours(
        self,
        entity: Optional[optional_arcade.arcade.Sprite],
    ) -> tuple[Optional[Any], Optional[Any]]:
        trigger = None
        hitbox = None
        for behaviour in self.get_zone_behaviours(entity):
            if trigger is None and is_trigger_behaviour(behaviour):
                trigger = behaviour
            elif hitbox is None and is_hitbox_behaviour(behaviour):
                hitbox = behaviour

        return trigger, hitbox

    def get_targeted_zone_behaviour(
        self,
        entity: Optional[optional_arcade.arcade.Sprite],
        behaviours: Optional[List[Any]] = None,
    ) -> Optional[Any]:
        if not entity:
            return None

        if behaviours is None:
            behaviours = self.get_zone_behaviours(entity)

        if not behaviours:
            return None

        predicate = is_trigger_behaviour if self._editor.zone_edit_target == ZONE_TARGET_TRIGGER else is_hitbox_behaviour
        for index, behaviour in enumerate(behaviours):
            if predicate(behaviour):
                self._editor.zone_behaviour_index = index
                return behaviour
        return None

    def toggle_zone_edit_target(self) -> bool:
        if not (self._editor.selected_entity and self._editor.tool_mode == TOOL_MODE_ZONE):
            return False

        trigger, hitbox = self.split_zone_behaviours(self._editor.selected_entity)
        if not (trigger and hitbox):
            return False

        self._editor.zone_edit_target = (
            ZONE_TARGET_HITBOX if self._editor.zone_edit_target == ZONE_TARGET_TRIGGER else ZONE_TARGET_TRIGGER
        )
        self.sync_zone_selection_state(self._editor.selected_entity)
        active = self.get_zone_behaviour(self._editor.selected_entity)
        if active:
            description = describe_zone_behaviour(active)
            logger.info("[Editor] Zone target toggled: %s", description)
        return True

    def get_patrol_behaviour(self, entity: optional_arcade.arcade.Sprite) -> Optional[Any]:
        behaviours = getattr(entity, "mesh_behaviours_runtime", [])
        for behaviour in behaviours:
            if behaviour.__class__.__name__ == "PatrolBehaviour":
                return behaviour
        return None

    def get_patrol_points(self, patrol_behaviour: Any) -> list:
        if hasattr(patrol_behaviour, "points"):
            return cast(list, patrol_behaviour.points)
        return []

    def add_waypoint(self, patrol_behaviour: Any, x: float, y: float) -> None:
        points = self.get_patrol_points(patrol_behaviour)
        old_points = list(points)
        points.append((x, y))

        entity_name = getattr(patrol_behaviour.entity, "mesh_name", "")
        self._editor._update_param_internal("patrol", "points", points, entity_name)
        logger.info("[Editor] Added waypoint at (%s, %s)", x, y)

        self._editor._push_command({
            "type": "ModifyPatrolPath",
            "entity_name": entity_name,
            "before": old_points,
            "after": list(points),
        })

    def remove_waypoint(self, behaviour: Any, index: int) -> None:
        points = self.get_patrol_points(behaviour)
        old_points = list(points)
        if 0 <= index < len(points):
            removed = points.pop(index)
            entity_name = getattr(behaviour.entity, "mesh_name", "")
            self._editor._update_param_internal("patrol", "points", points, entity_name)
            logger.info("[Editor] Removed waypoint at %s", removed)

            self._editor._push_command({
                "type": "ModifyPatrolPath",
                "entity_name": entity_name,
                "before": old_points,
                "after": list(points),
            })

    def move_waypoint(self, behaviour: Any, index: int, dx: float, dy: float) -> None:
        points = self.get_patrol_points(behaviour)
        old_points = list(points)
        if 0 <= index < len(points):
            px, py = points[index]
            points[index] = (px + dx, py + dy)
            entity_name = getattr(behaviour.entity, "mesh_name", "")
            self._editor._update_param_internal("patrol", "points", points, entity_name)

            self._editor._push_command({
                "type": "ModifyPatrolPath",
                "entity_name": entity_name,
                "before": old_points,
                "after": list(points),
            })

    def get_zone_behaviours(self, entity: Optional[optional_arcade.arcade.Sprite]) -> List[Any]:
        if not entity:
            return []

        behaviours = getattr(entity, "mesh_behaviours_runtime", [])
        zone_behaviours: List[Any] = []
        for behaviour in behaviours:
            if is_trigger_behaviour(behaviour) or is_hitbox_behaviour(behaviour):
                zone_behaviours.append(behaviour)
        return zone_behaviours

    def get_zone_behaviour(self, entity: Optional[optional_arcade.arcade.Sprite]) -> Optional[Any]:
        behaviours = self.get_zone_behaviours(entity)
        if not behaviours:
            return None

        targeted = self.get_targeted_zone_behaviour(entity, behaviours)
        if targeted:
            return targeted

        max_index = len(behaviours) - 1
        self._editor.zone_behaviour_index = max(0, min(self._editor.zone_behaviour_index, max_index))
        chosen = behaviours[self._editor.zone_behaviour_index]
        self._editor.zone_edit_target = infer_zone_target_from_behaviour(chosen)
        return chosen

    def cycle_zone_behaviour(self) -> bool:
        if not self._editor.selected_entity:
            return False

        behaviours = self.get_zone_behaviours(self._editor.selected_entity)
        if not behaviours:
            logger.info("[Editor] No zone behaviours on selected entity.")
            return False

        if len(behaviours) == 1:
            description = describe_zone_behaviour(behaviours[0])
            self._editor.zone_edit_target = infer_zone_target_from_behaviour(behaviours[0])
            logger.info("[Editor] Single zone target active: %s", description)
            return True

        self._editor.zone_behaviour_index = (self._editor.zone_behaviour_index + 1) % len(behaviours)
        behaviour = behaviours[self._editor.zone_behaviour_index]
        self._editor.zone_edit_target = infer_zone_target_from_behaviour(behaviour)
        description = describe_zone_behaviour(behaviour)
        logger.info(
            "[Editor] Zone target: %s (%s/%s)",
            description,
            self._editor.zone_behaviour_index + 1,
            len(behaviours),
        )
        return True

    def resize_zone(self, behaviour: Any, dx: float, dy: float) -> None:
        entity_name = getattr(behaviour.entity, "mesh_name", "")

        if is_trigger_behaviour(behaviour):
            current = getattr(behaviour, "radius", 0.0)
            delta = dx if abs(dx) > abs(dy) else dy
            new_radius = max(0.0, current + delta)

            behaviour.radius = new_radius
            self._editor._update_param_internal("trigger_zone", "trigger_radius", new_radius, entity_name)
            logger.info("[Editor] Trigger radius: %s", new_radius)

            self._editor._push_command({
                "type": "ResizeZone",
                "entity_name": entity_name,
                "before": current,
                "after": new_radius,
            })

        elif is_hitbox_behaviour(behaviour):
            w = getattr(behaviour, "width", 0.0)
            h = getattr(behaviour, "height", 0.0)

            new_w = max(0.0, w + dx)
            new_h = max(0.0, h + dy)

            behaviour.width = new_w
            behaviour.height = new_h
            self._editor._update_param_internal("hitbox", "width", new_w, entity_name)
            self._editor._update_param_internal("hitbox", "height", new_h, entity_name)
            logger.info("[Editor] Hitbox size: %s x %s", new_w, new_h)

            self._editor._push_command({
                "type": "ResizeHitbox",
                "entity_name": entity_name,
                "before": {"width": w, "height": h},
                "after": {"width": new_w, "height": new_h},
            })
