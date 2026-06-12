"""TriggerVolume behaviour - polygon/rect trigger with enter/exit events.

Detects when entities enter or exit a defined volume and emits deterministic
events. Supports both rectangular and polygon-based trigger volumes.

Events emitted:
- on_enter: When an entity enters the volume
- on_exit: When an entity exits the volume

Save/restore:
- Tracks which entities are currently inside the volume
- Deterministic event ordering on restore
"""

from __future__ import annotations

from typing import Any, Dict, List, Set, Tuple

from ..event_emit import emit_gameplay_event
from ..gameplay_event_bus import EventConfigError, validate_event_type
from .base import Behaviour, ParamDef
from .registry import register_behaviour


def _point_in_rect(
    px: float,
    py: float,
    rect_x: float,
    rect_y: float,
    rect_width: float,
    rect_height: float,
) -> bool:
    """Check if a point is inside a rectangle."""
    return (
        rect_x <= px <= rect_x + rect_width
        and rect_y <= py <= rect_y + rect_height
    )


def _point_in_polygon(px: float, py: float, polygon: List[Tuple[float, float]]) -> bool:
    """Check if a point is inside a polygon using ray casting."""
    if len(polygon) < 3:
        return False

    inside = False
    n = len(polygon)
    j = n - 1

    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]

        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            inside = not inside
        j = i

    return inside


@register_behaviour(
    "TriggerVolume",
    description="Detects entities entering/exiting a rectangular or polygon volume.",
    config_fields=[
        {
            "name": "volume_type",
            "description": "Type of volume: 'rect' or 'polygon'",
            "type": "string",
            "default": "rect",
        },
        {
            "name": "width",
            "description": "Width of rectangular volume (if volume_type='rect')",
            "type": "float",
            "default": 64.0,
        },
        {
            "name": "height",
            "description": "Height of rectangular volume (if volume_type='rect')",
            "type": "float",
            "default": 64.0,
        },
        {
            "name": "polygon",
            "description": "List of [x, y] points relative to entity (if volume_type='polygon')",
            "type": "array",
            "default": [],
        },
        {
            "name": "target_tags",
            "description": "List of entity tags that can trigger (empty = all)",
            "type": "array",
            "default": [],
        },
        {
            "name": "target_name",
            "description": "Specific entity name to watch (empty = use tags)",
            "type": "string",
            "default": "",
        },
        {
            "name": "on_enter_event",
            "description": "Event type to emit on enter (empty = 'on_enter')",
            "type": "string",
            "default": "on_enter",
        },
        {
            "name": "on_exit_event",
            "description": "Event type to emit on exit (empty = 'on_exit')",
            "type": "string",
            "default": "on_exit",
        },
        {
            "name": "one_shot",
            "description": "If true, only fire enter once per entity",
            "type": "bool",
            "default": False,
        },
        {
            "name": "enabled",
            "description": "Whether the trigger is active",
            "type": "bool",
            "default": True,
        },
    ],
)
class TriggerVolumeBehaviour(Behaviour):
    """Polygon/rect trigger with on_enter/on_exit events.
    
    Implements SaveableBehaviour for deterministic save/restore.
    """

    PARAM_DEFS = {
        "volume_type": ParamDef(str, "rect", "Type of volume: 'rect' or 'polygon'"),
        "width": ParamDef(float, 64.0, "Width of rectangular volume"),
        "height": ParamDef(float, 64.0, "Height of rectangular volume"),
        "polygon": ParamDef(list, [], "List of [x, y] points for polygon"),
        "target_tags": ParamDef(list, [], "Entity tags that can trigger"),
        "target_name": ParamDef(str, "", "Specific entity name to watch"),
        "on_enter_event": ParamDef(str, "on_enter", "Event type to emit on enter"),
        "on_exit_event": ParamDef(str, "on_exit", "Event type to emit on exit"),
        "one_shot": ParamDef(bool, False, "Only fire enter once per entity"),
        "enabled": ParamDef(bool, True, "Whether the trigger is active"),
    }

    def __init__(self, entity, window, **config) -> None:
        # Initialize private state before super().__init__ (which calls setattr for params)
        self._enabled: bool = True
        self._entities_inside: Set[str] = set()
        self._fired_entities: Set[str] = set()

        super().__init__(entity, window, **config)

        # Config
        self.volume_type = str(self.config.get("volume_type", "rect"))
        self.width = float(self.config.get("width", 64.0))
        self.height = float(self.config.get("height", 64.0))
        self.target_tags = list(self.config.get("target_tags") or [])
        self.target_name = str(self.config.get("target_name", "")).strip()
        self.on_enter_event = str(self.config.get("on_enter_event", "on_enter"))
        self.on_exit_event = str(self.config.get("on_exit_event", "on_exit"))
        self.one_shot = bool(self.config.get("one_shot", False))
        self._enabled = bool(self.config.get("enabled", True))

        # Parse polygon
        raw_polygon = self.config.get("polygon") or []
        self._polygon: List[Tuple[float, float]] = []
        if isinstance(raw_polygon, list):
            for point in raw_polygon:
                if isinstance(point, (list, tuple)) and len(point) >= 2:
                    try:
                        self._polygon.append((float(point[0]), float(point[1])))
                    except (TypeError, ValueError):
                        pass

    @property
    def enabled(self) -> bool:
        """Whether the trigger is active."""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = bool(value)

    def _get_volume_bounds(self) -> Tuple[float, float, float, float]:
        """Get world-space bounds of the trigger volume."""
        cx = float(self.entity.center_x)
        cy = float(self.entity.center_y)

        if self.volume_type == "polygon" and self._polygon:
            # Use polygon bounding box
            xs = [p[0] + cx for p in self._polygon]
            ys = [p[1] + cy for p in self._polygon]
            return (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))

        # Rectangle centered on entity
        half_w = self.width / 2
        half_h = self.height / 2
        return (cx - half_w, cy - half_h, self.width, self.height)

    def _is_point_inside(self, px: float, py: float) -> bool:
        """Check if a point is inside the trigger volume."""
        cx = float(self.entity.center_x)
        cy = float(self.entity.center_y)

        if self.volume_type == "polygon" and self._polygon:
            # Transform polygon to world space
            world_polygon = [(p[0] + cx, p[1] + cy) for p in self._polygon]
            return _point_in_polygon(px, py, world_polygon)

        # Rectangle
        half_w = self.width / 2
        half_h = self.height / 2
        return _point_in_rect(px, py, cx - half_w, cy - half_h, self.width, self.height)

    def _should_track_entity(self, sprite) -> bool:
        """Check if an entity should be tracked by this trigger."""
        if sprite is self.entity:
            return False

        entity_id = getattr(sprite, "mesh_id", None) or getattr(sprite, "mesh_name", None)
        if not entity_id:
            return False

        # Check specific name
        if self.target_name:
            name = getattr(sprite, "mesh_name", "")
            return name == self.target_name

        # Check tags
        if self.target_tags:
            entity_tags = set(getattr(sprite, "mesh_tags", []) or [])
            return bool(entity_tags & set(self.target_tags))

        # Track all entities if no filter
        return True

    def _get_entity_id(self, sprite) -> str:
        """Get deterministic ID for an entity."""
        return str(
            getattr(sprite, "mesh_id", None)
            or getattr(sprite, "mesh_name", None)
            or id(sprite)
        )

    def _emit_event(self, event_type: str, entity_id: str, sprite) -> None:
        """Emit a gameplay event."""
        my_id = getattr(self.entity, "mesh_id", "")
        payload = {
            "zone": my_id,
            "zone_name": getattr(self.entity, "mesh_name", ""),
            "entity": entity_id,
            "entity_name": getattr(sprite, "mesh_name", ""),
            "position": (float(sprite.center_x), float(sprite.center_y)),
        }
        emit_gameplay_event(
            self.window,
            event_type,
            payload,
            source_entity_id=my_id,
            source_behaviour="TriggerVolume",
        )

    def update(self, dt: float) -> None:
        """Check for entities entering/exiting the volume."""
        if not self._enabled:
            return

        # Get all sprites in the scene
        scene_controller = getattr(self.window, "scene_controller", None)
        if scene_controller is None:
            return

        sprites = getattr(scene_controller, "all_sprites", None)
        if sprites is None:
            sprites = getattr(scene_controller, "entities", None)
        if sprites is None:
            return

        # Track current frame's entities inside
        current_inside: Set[str] = set()
        entity_map: Dict[str, Any] = {}

        for sprite in sprites:
            if not self._should_track_entity(sprite):
                continue

            entity_id = self._get_entity_id(sprite)
            px = float(sprite.center_x)
            py = float(sprite.center_y)

            if self._is_point_inside(px, py):
                current_inside.add(entity_id)
                entity_map[entity_id] = sprite

        # Deterministic ordering: sort by entity ID
        sorted_ids = sorted(current_inside | self._entities_inside)

        # Check for enters (deterministic order)
        for entity_id in sorted_ids:
            if entity_id in current_inside and entity_id not in self._entities_inside:
                # Entity just entered
                if self.one_shot and entity_id in self._fired_entities:
                    continue

                sprite = entity_map.get(entity_id)
                if sprite is not None:
                    self._emit_event(self.on_enter_event, entity_id, sprite)
                    self._fired_entities.add(entity_id)

        # Check for exits (deterministic order)
        for entity_id in sorted_ids:
            if entity_id in self._entities_inside and entity_id not in current_inside:
                my_id = getattr(self.entity, "mesh_id", "")
                payload = {
                    "zone": my_id,
                    "zone_name": getattr(self.entity, "mesh_name", ""),
                    "entity": entity_id,
                }
                emit_gameplay_event(
                    self.window,
                    self.on_exit_event,
                    payload,
                    source_entity_id=my_id,
                    source_behaviour="TriggerVolume",
                )

        # Update state
        self._entities_inside = current_inside

    # SaveableBehaviour protocol
    def saveable_state(self) -> Dict[str, Any]:
        """Return JSON-serializable state dict."""
        return {
            "enabled": self._enabled,
            "entities_inside": sorted(self._entities_inside),
            "fired_entities": sorted(self._fired_entities),
        }

    def restore_state(self, state: Dict[str, Any]) -> None:
        """Apply previously saved state."""
        self._enabled = bool(state.get("enabled", True))
        self._entities_inside = set(state.get("entities_inside") or [])
        self._fired_entities = set(state.get("fired_entities") or [])

    def get_inspector_state(self) -> Dict[str, Any]:
        """Return state summary for editor inspection."""
        return {
            "enabled": self._enabled,
            "volume_type": self.volume_type,
            "volume_size": f"{self.width}x{self.height}" if self.volume_type == "rect" else f"{len(self._polygon)} points",
            "entities_inside": len(self._entities_inside),
            "entities_inside_list": sorted(self._entities_inside)[:5],  # Show first 5
            "fired_count": len(self._fired_entities),
        }


def validate_trigger_volume_config(
    config: Dict[str, Any],
    *,
    entity_id: str = "",
) -> List[EventConfigError]:
    """Validate TriggerVolume configuration.
    
    Args:
        config: Configuration dictionary.
        entity_id: Entity ID for error reporting.
        
    Returns:
        List of validation errors.
    """
    errors: List[EventConfigError] = []
    behaviour_name = "TriggerVolume"

    # Validate volume_type
    volume_type = config.get("volume_type", "rect")
    if volume_type not in ("rect", "polygon"):
        errors.append(EventConfigError(
            entity_id=entity_id,
            behaviour_name=behaviour_name,
            config_path="volume_type",
            message=f"volume_type must be 'rect' or 'polygon', got '{volume_type}'",
        ))

    # Validate dimensions for rect
    if volume_type == "rect":
        width = config.get("width", 64.0)
        height = config.get("height", 64.0)

        try:
            width = float(width)
            if width <= 0:
                errors.append(EventConfigError(
                    entity_id=entity_id,
                    behaviour_name=behaviour_name,
                    config_path="width",
                    message="width must be positive",
                ))
        except (TypeError, ValueError):
            errors.append(EventConfigError(
                entity_id=entity_id,
                behaviour_name=behaviour_name,
                config_path="width",
                message=f"width must be a number, got {type(width).__name__}",
            ))

        try:
            height = float(height)
            if height <= 0:
                errors.append(EventConfigError(
                    entity_id=entity_id,
                    behaviour_name=behaviour_name,
                    config_path="height",
                    message="height must be positive",
                ))
        except (TypeError, ValueError):
            errors.append(EventConfigError(
                entity_id=entity_id,
                behaviour_name=behaviour_name,
                config_path="height",
                message=f"height must be a number, got {type(height).__name__}",
            ))

    # Validate polygon for polygon type
    if volume_type == "polygon":
        polygon = config.get("polygon", [])
        if not isinstance(polygon, list):
            errors.append(EventConfigError(
                entity_id=entity_id,
                behaviour_name=behaviour_name,
                config_path="polygon",
                message="polygon must be a list of points",
            ))
        elif len(polygon) < 3:
            errors.append(EventConfigError(
                entity_id=entity_id,
                behaviour_name=behaviour_name,
                config_path="polygon",
                message="polygon must have at least 3 points",
            ))
        else:
            for i, point in enumerate(polygon):
                if not isinstance(point, (list, tuple)) or len(point) < 2:
                    errors.append(EventConfigError(
                        entity_id=entity_id,
                        behaviour_name=behaviour_name,
                        config_path=f"polygon[{i}]",
                        message="each polygon point must be [x, y]",
                    ))

    # Validate event types
    on_enter = config.get("on_enter_event", "on_enter")
    if on_enter:
        errors.extend(validate_event_type(
            on_enter,
            entity_id=entity_id,
            behaviour_name=behaviour_name,
            config_path="on_enter_event",
        ))

    on_exit = config.get("on_exit_event", "on_exit")
    if on_exit:
        errors.extend(validate_event_type(
            on_exit,
            entity_id=entity_id,
            behaviour_name=behaviour_name,
            config_path="on_exit_event",
        ))

    return errors
