"""PatrolPath behaviour - deterministic waypoint-based patrol.

Provides ordered waypoint patrol with loop/pingpong modes and event emissions.
All movement is deterministic based on delta time.

Events emitted:
- patrol_started: When patrol begins
- reached_waypoint: When a waypoint is reached
- patrol_completed: When all waypoints visited (non-loop modes)

Save/restore:
- Tracks current waypoint index, direction, stuck counter
- Fully deterministic on restore
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Set, Tuple

from ..event_emit import emit_gameplay_event
from ..gameplay_event_bus import EventConfigError, validate_event_type
from .base import Behaviour, ParamDef
from .registry import register_behaviour


# =============================================================================
# Constants
# =============================================================================

PATROL_MODES = frozenset({"loop", "pingpong", "once"})


# =============================================================================
# PatrolPath Behaviour
# =============================================================================

@register_behaviour(
    "PatrolPath",
    description="Patrols between waypoints with loop/pingpong modes.",
    config_fields=[
        {
            "name": "waypoints",
            "description": "List of {x, y} or marker names",
            "type": "array",
            "default": [],
        },
        {
            "name": "waypoint_tag",
            "description": "If set, discover waypoints by mesh_tag (sorted by x then y)",
            "type": "string",
            "default": "",
        },
        {
            "name": "speed",
            "description": "Movement speed in units per second",
            "type": "float",
            "default": 60.0,
        },
        {
            "name": "mode",
            "description": "Patrol mode: 'loop', 'pingpong', or 'once'",
            "type": "string",
            "default": "loop",
        },
        {
            "name": "arrive_radius",
            "description": "Distance to consider a waypoint reached",
            "type": "float",
            "default": 4.0,
        },
        {
            "name": "wait_time",
            "description": "Time to wait at each waypoint (0 = no wait)",
            "type": "float",
            "default": 0.0,
        },
        {
            "name": "start_on_create",
            "description": "Start patrol immediately on creation",
            "type": "bool",
            "default": True,
        },
        {
            "name": "enabled",
            "description": "Whether the patrol is active",
            "type": "bool",
            "default": True,
        },
    ],
)
class PatrolPathBehaviour(Behaviour):
    """Patrols between waypoints with loop/pingpong modes.
    
    Implements SaveableBehaviour for deterministic save/restore.
    
    Waypoints can be specified as:
    - List of {x, y} dicts
    - List of named marker entity IDs
    - Auto-discovered via waypoint_tag
    """
    
    STATE_VERSION = 1
    
    PARAM_DEFS = {
        "waypoints": ParamDef(list, [], "List of waypoints"),
        "waypoint_tag": ParamDef(str, "", "Discover waypoints by mesh_tag"),
        "speed": ParamDef(float, 60.0, "Movement speed"),
        "mode": ParamDef(str, "loop", "Patrol mode: loop/pingpong/once"),
        "arrive_radius": ParamDef(float, 4.0, "Arrival distance"),
        "wait_time": ParamDef(float, 0.0, "Wait time at waypoints"),
        "start_on_create": ParamDef(bool, True, "Auto-start patrol"),
        "enabled": ParamDef(bool, True, "Whether active"),
    }
    
    def __init__(self, entity, window, **config) -> None:
        # Initialize private state before super().__init__
        self._enabled: bool = True
        self._state: str = "idle"  # idle|patrolling|waiting|completed
        self._waypoints: List[Tuple[float, float]] = []
        self._waypoint_index: int = 0
        self._direction: int = 1  # 1=forward, -1=backward (pingpong)
        self._wait_remaining: float = 0.0
        self._stuck_counter: int = 0
        self._last_pos: Optional[Tuple[float, float]] = None
        self._started: bool = False
        self._waypoints_resolved: bool = False
        
        super().__init__(entity, window, **config)
        
        # Config
        self._raw_waypoints = list(self.config.get("waypoints", []))
        self._waypoint_tag = str(self.config.get("waypoint_tag", "")).strip()
        self.speed = max(0.0, float(self.config.get("speed", 60.0)))
        mode = str(self.config.get("mode", "loop")).strip().lower()
        self.mode = mode if mode in PATROL_MODES else "loop"
        self.arrive_radius = max(0.1, float(self.config.get("arrive_radius", 4.0)))
        self.wait_time = max(0.0, float(self.config.get("wait_time", 0.0)))
        self.start_on_create = bool(self.config.get("start_on_create", True))
        self._enabled = bool(self.config.get("enabled", True))
        
        # Auto-start if configured
        if self.start_on_create and self._enabled:
            self._state = "patrolling"
    
    @property
    def enabled(self) -> bool:
        """Whether the patrol is active."""
        return self._enabled
    
    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = bool(value)
    
    @property
    def state(self) -> str:
        """Current patrol state: idle, patrolling, waiting, completed."""
        return self._state
    
    @property
    def current_waypoint_index(self) -> int:
        """Index of current target waypoint."""
        return self._waypoint_index
    
    @property
    def waypoint_count(self) -> int:
        """Total number of waypoints."""
        return len(self._waypoints)
    
    @property
    def is_patrolling(self) -> bool:
        """Whether patrol is actively running."""
        return self._state in ("patrolling", "waiting")
    
    def start(self) -> None:
        """Start or resume patrolling."""
        if not self._waypoints and not self._waypoints_resolved:
            self._resolve_waypoints()
        
        if not self._waypoints:
            self._state = "idle"
            return
        
        self._state = "patrolling"
        if not self._started:
            self._started = True
            self._emit_event(
                "patrol_started",
                waypoint_count=len(self._waypoints),
                mode=self.mode,
            )
    
    def stop(self) -> None:
        """Stop patrolling."""
        self._state = "idle"
    
    def reset(self) -> None:
        """Reset patrol to initial state."""
        self._waypoint_index = 0
        self._direction = 1
        self._wait_remaining = 0.0
        self._stuck_counter = 0
        self._last_pos = None
        self._started = False
        self._state = "idle"
    
    def _resolve_waypoints(self) -> None:
        """Resolve waypoint definitions to world coordinates."""
        self._waypoints_resolved = True
        self._waypoints = []
        
        # First try tag-based discovery
        if self._waypoint_tag:
            self._resolve_waypoints_by_tag()
            if self._waypoints:
                return
        
        # Parse raw waypoints
        for wp in self._raw_waypoints:
            coords = self._parse_waypoint(wp)
            if coords is not None:
                self._waypoints.append(coords)
    
    def _resolve_waypoints_by_tag(self) -> None:
        """Discover waypoints by mesh_tag, sorted deterministically."""
        scene = getattr(self.window, "scene_controller", None)
        if scene is None:
            return
        
        sprites = getattr(scene, "all_sprites", None)
        if sprites is None:
            return
        
        # Collect matching sprites
        matching: List[Tuple[float, float, str]] = []
        for sprite in sprites:
            if sprite is self.entity:
                continue
            tags = getattr(sprite, "mesh_tags", []) or []
            if self._waypoint_tag not in tags:
                continue
            
            x = float(getattr(sprite, "center_x", 0.0))
            y = float(getattr(sprite, "center_y", 0.0))
            entity_id = str(
                getattr(sprite, "mesh_id", None)
                or getattr(sprite, "mesh_name", None)
                or ""
            )
            matching.append((x, y, entity_id))
        
        # Sort deterministically: by x, then y, then id
        matching.sort(key=lambda t: (t[0], t[1], t[2]))
        self._waypoints = [(x, y) for x, y, _ in matching]
    
    def _parse_waypoint(self, wp: Any) -> Optional[Tuple[float, float]]:
        """Parse a single waypoint definition.
        
        Supports:
        - {x: float, y: float}
        - [x, y]
        - "marker_entity_id"
        """
        if isinstance(wp, dict):
            try:
                return (float(wp.get("x", 0.0)), float(wp.get("y", 0.0)))
            except (TypeError, ValueError):
                return None
        
        if isinstance(wp, (list, tuple)) and len(wp) >= 2:
            try:
                return (float(wp[0]), float(wp[1]))
            except (TypeError, ValueError):
                return None
        
        if isinstance(wp, str) and wp.strip():
            # Look up by entity ID/name
            return self._resolve_marker(wp.strip())
        
        return None
    
    def _resolve_marker(self, marker_id: str) -> Optional[Tuple[float, float]]:
        """Resolve a marker entity ID to world coordinates."""
        scene = getattr(self.window, "scene_controller", None)
        if scene is None:
            return None
        
        # Try scene index first
        idx = getattr(scene, "_scene_index", None)
        if idx is not None:
            getter = getattr(idx, "get_by_id", None)
            if callable(getter):
                sprite = getter(marker_id)
                if sprite is not None:
                    return (
                        float(getattr(sprite, "center_x", 0.0)),
                        float(getattr(sprite, "center_y", 0.0)),
                    )
        
        # Fallback: search all sprites
        sprites = getattr(scene, "all_sprites", None)
        if sprites is None:
            return None
        
        for sprite in sprites:
            entity_id = (
                getattr(sprite, "mesh_id", None)
                or getattr(sprite, "mesh_name", None)
            )
            if str(entity_id or "") == marker_id:
                return (
                    float(getattr(sprite, "center_x", 0.0)),
                    float(getattr(sprite, "center_y", 0.0)),
                )
        
        return None
    
    def _emit_event(self, event_type: str, **kwargs) -> None:
        """Emit a gameplay event."""
        my_id = getattr(self.entity, "mesh_id", "")
        
        payload = {
            "entity": my_id,
            "entity_name": getattr(self.entity, "mesh_name", ""),
            "waypoint_index": self._waypoint_index,
            **kwargs,
        }
        
        emit_gameplay_event(
            self.window,
            event_type,
            payload,
            source_entity_id=my_id,
            source_behaviour="PatrolPath",
        )
    
    def update(self, dt: float) -> None:
        """Update patrol state."""
        if dt <= 0:
            return
        if not self._enabled:
            return
        if self._state == "idle" or self._state == "completed":
            return
        
        # Lazy resolve waypoints
        if not self._waypoints_resolved:
            self._resolve_waypoints()
        
        if not self._waypoints:
            self._state = "idle"
            return
        
        # Handle waiting state
        if self._state == "waiting":
            self._wait_remaining -= dt
            if self._wait_remaining <= 0:
                self._wait_remaining = 0.0
                self._advance_waypoint()
            return
        
        # Patrolling state
        if self._state != "patrolling":
            return
        
        # Get current position
        ex = float(getattr(self.entity, "center_x", 0.0))
        ey = float(getattr(self.entity, "center_y", 0.0))
        
        # Check stuck detection
        if self._last_pos is not None:
            if abs(ex - self._last_pos[0]) < 0.01 and abs(ey - self._last_pos[1]) < 0.01:
                self._stuck_counter += 1
            else:
                self._stuck_counter = 0
        self._last_pos = (ex, ey)
        
        # Get target waypoint
        if self._waypoint_index >= len(self._waypoints):
            self._waypoint_index = 0
        
        target = self._waypoints[self._waypoint_index]
        tx, ty = target
        
        # Check arrival
        dist = math.hypot(tx - ex, ty - ey)
        if dist <= self.arrive_radius:
            self._on_waypoint_reached()
            return
        
        # Move toward waypoint
        step = self.speed * dt
        if step >= dist:
            move_x = tx - ex
            move_y = ty - ey
        else:
            nx = (tx - ex) / dist
            ny = (ty - ey) / dist
            move_x = nx * step
            move_y = ny * step
        
        # Apply movement
        scene = getattr(self.window, "scene_controller", None)
        mover = getattr(scene, "move_entity_with_collision", None) if scene else None
        if callable(mover):
            mover(self.entity, move_x, move_y)
        else:
            self.entity.center_x = ex + move_x
            self.entity.center_y = ey + move_y
    
    def _on_waypoint_reached(self) -> None:
        """Handle reaching a waypoint."""
        self._emit_event(
            "reached_waypoint",
            waypoint_index=self._waypoint_index,
            waypoint_position=self._waypoints[self._waypoint_index],
        )
        
        # Enter wait state if configured
        if self.wait_time > 0:
            self._state = "waiting"
            self._wait_remaining = self.wait_time
        else:
            self._advance_waypoint()
    
    def _advance_waypoint(self) -> None:
        """Advance to the next waypoint."""
        if not self._waypoints:
            self._state = "idle"
            return
        
        if self.mode == "loop":
            self._waypoint_index = (self._waypoint_index + 1) % len(self._waypoints)
            self._state = "patrolling"
        
        elif self.mode == "pingpong":
            next_idx = self._waypoint_index + self._direction
            if next_idx >= len(self._waypoints):
                self._direction = -1
                next_idx = len(self._waypoints) - 2
            elif next_idx < 0:
                self._direction = 1
                next_idx = 1
            
            self._waypoint_index = max(0, min(next_idx, len(self._waypoints) - 1))
            self._state = "patrolling"
        
        elif self.mode == "once":
            next_idx = self._waypoint_index + 1
            if next_idx >= len(self._waypoints):
                self._state = "completed"
                self._emit_event("patrol_completed")
            else:
                self._waypoint_index = next_idx
                self._state = "patrolling"
    
    # =========================================================================
    # SaveableBehaviour Protocol
    # =========================================================================
    
    def saveable_state(self) -> Dict[str, Any]:
        """Return JSON-serializable state dict."""
        return {
            "_version": self.STATE_VERSION,
            "state": self._state,
            "waypoint_index": self._waypoint_index,
            "direction": self._direction,
            "wait_remaining": self._wait_remaining,
            "stuck_counter": self._stuck_counter,
            "started": self._started,
            "waypoints_resolved": self._waypoints_resolved,
            "waypoints": list(self._waypoints),
        }
    
    def restore_state(self, state: Dict[str, Any]) -> None:
        """Apply previously saved state."""
        self._state = str(state.get("state", "idle"))
        self._waypoint_index = int(state.get("waypoint_index", 0))
        self._direction = int(state.get("direction", 1))
        self._wait_remaining = float(state.get("wait_remaining", 0.0))
        self._stuck_counter = int(state.get("stuck_counter", 0))
        self._started = bool(state.get("started", False))
        self._waypoints_resolved = bool(state.get("waypoints_resolved", False))
        
        # Restore waypoints if saved
        raw_wps = state.get("waypoints", [])
        if isinstance(raw_wps, list):
            self._waypoints = []
            for wp in raw_wps:
                if isinstance(wp, (list, tuple)) and len(wp) >= 2:
                    try:
                        self._waypoints.append((float(wp[0]), float(wp[1])))
                    except (TypeError, ValueError):
                        pass
        
        self._last_pos = None
    
    # =========================================================================
    # Inspector Support
    # =========================================================================
    
    def get_inspector_state(self) -> Dict[str, Any]:
        """Return state for editor inspector."""
        current_wp = None
        if self._waypoints and 0 <= self._waypoint_index < len(self._waypoints):
            current_wp = self._waypoints[self._waypoint_index]
        
        return {
            "state": self._state,
            "waypoint_index": self._waypoint_index,
            "waypoint_count": len(self._waypoints),
            "current_waypoint": current_wp,
            "direction": "forward" if self._direction == 1 else "backward",
            "mode": self.mode,
            "speed": self.speed,
            "wait_remaining": self._wait_remaining,
            "stuck_counter": self._stuck_counter,
        }


# =============================================================================
# Config Validation
# =============================================================================

def validate_patrol_path_config(
    config: Dict[str, Any],
    *,
    entity_id: str = "",
) -> List[EventConfigError]:
    """Validate PatrolPath configuration.
    
    Args:
        config: Configuration dictionary.
        entity_id: Entity ID for error reporting.
        
    Returns:
        List of validation errors.
    """
    errors: List[EventConfigError] = []
    behaviour_name = "PatrolPath"
    
    # Validate waypoints
    waypoints = config.get("waypoints", [])
    waypoint_tag = config.get("waypoint_tag", "")
    
    if not waypoints and not waypoint_tag:
        errors.append(EventConfigError(
            entity_id=entity_id,
            behaviour_name=behaviour_name,
            config_path="waypoints",
            message="either waypoints or waypoint_tag must be specified",
        ))
    
    if waypoints and not isinstance(waypoints, list):
        errors.append(EventConfigError(
            entity_id=entity_id,
            behaviour_name=behaviour_name,
            config_path="waypoints",
            message=f"waypoints must be a list, got {type(waypoints).__name__}",
        ))
    
    # Validate mode
    mode = config.get("mode", "loop")
    if mode and str(mode).strip().lower() not in PATROL_MODES:
        errors.append(EventConfigError(
            entity_id=entity_id,
            behaviour_name=behaviour_name,
            config_path="mode",
            message=f"invalid mode: {mode!r}. Valid modes: {sorted(PATROL_MODES)}",
        ))
    
    # Validate speed
    speed = config.get("speed", 60.0)
    try:
        speed_val = float(speed)
        if speed_val < 0:
            errors.append(EventConfigError(
                entity_id=entity_id,
                behaviour_name=behaviour_name,
                config_path="speed",
                message="speed must be non-negative",
            ))
    except (TypeError, ValueError):
        errors.append(EventConfigError(
            entity_id=entity_id,
            behaviour_name=behaviour_name,
            config_path="speed",
            message=f"speed must be a number, got {type(speed).__name__}",
        ))
    
    # Validate arrive_radius
    arrive = config.get("arrive_radius", 4.0)
    try:
        arrive_val = float(arrive)
        if arrive_val <= 0:
            errors.append(EventConfigError(
                entity_id=entity_id,
                behaviour_name=behaviour_name,
                config_path="arrive_radius",
                message="arrive_radius must be positive",
            ))
    except (TypeError, ValueError):
        errors.append(EventConfigError(
            entity_id=entity_id,
            behaviour_name=behaviour_name,
            config_path="arrive_radius",
            message=f"arrive_radius must be a number, got {type(arrive).__name__}",
        ))
    
    return errors
