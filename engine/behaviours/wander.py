"""Wander behaviour - deterministic random movement.

Provides random wandering within bounds using RNGService for deterministic
movement decisions. Useful for ambient AI movement.

Events emitted:
- wander_started: When wander begins
- wander_point_reached: When a wander point is reached
- wander_stopped: When wander stops

Save/restore:
- Tracks current wander target, path state, cooldown
- Fully deterministic on restore (RNG state not saved - use RNGService seeding)
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from ..event_emit import emit_gameplay_event
from ..gameplay_event_bus import EventConfigError
from ..pathfinding import NavGrid, astar
from ..singletons import get_registry
from .base import Behaviour, ParamDef
from .registry import register_behaviour


# =============================================================================
# Constants
# =============================================================================

# RNG stream name for deterministic wander point selection
WANDER_RNG_STREAM = "ai_wander"


# =============================================================================
# Wander Behaviour
# =============================================================================

@register_behaviour(
    "Wander",
    description="Randomly wanders within a radius using pathfinding.",
    config_fields=[
        {
            "name": "wander_radius",
            "description": "Maximum distance in tiles from origin to wander",
            "type": "float",
            "default": 5.0,
        },
        {
            "name": "min_wander_distance",
            "description": "Minimum distance in tiles for each wander move",
            "type": "float",
            "default": 2.0,
        },
        {
            "name": "speed",
            "description": "Movement speed while wandering",
            "type": "float",
            "default": 40.0,
        },
        {
            "name": "idle_time_min",
            "description": "Minimum time to idle between wanders (seconds)",
            "type": "float",
            "default": 1.0,
        },
        {
            "name": "idle_time_max",
            "description": "Maximum time to idle between wanders (seconds)",
            "type": "float",
            "default": 3.0,
        },
        {
            "name": "anchor_to_spawn",
            "description": "If true, anchor to spawn position; else current position",
            "type": "bool",
            "default": True,
        },
        {
            "name": "max_path_attempts",
            "description": "Maximum attempts to find a valid wander path",
            "type": "int",
            "default": 5,
        },
        {
            "name": "enabled",
            "description": "Whether wander is active",
            "type": "bool",
            "default": True,
        },
    ],
)
class WanderBehaviour(Behaviour):
    """Random wandering within bounds.
    
    Implements SaveableBehaviour for deterministic save/restore.
    Uses RNGService for deterministic wander point selection.
    """
    
    STATE_VERSION = 1
    
    PARAM_DEFS = {
        "wander_radius": ParamDef(float, 5.0, "Max wander distance in tiles"),
        "min_wander_distance": ParamDef(float, 2.0, "Min wander distance"),
        "speed": ParamDef(float, 40.0, "Wander movement speed"),
        "idle_time_min": ParamDef(float, 1.0, "Min idle time"),
        "idle_time_max": ParamDef(float, 3.0, "Max idle time"),
        "anchor_to_spawn": ParamDef(bool, True, "Anchor to spawn position"),
        "max_path_attempts": ParamDef(int, 5, "Max path finding attempts"),
        "enabled": ParamDef(bool, True, "Whether active"),
    }

    def __init__(self, entity, window, **config: Any) -> None:
        # Initialize private state before super().__init__
        self._enabled: bool = True
        self._state: str = "idle"  # idle|wandering
        self._origin: Optional[Tuple[float, float]] = None
        self._wander_target: Optional[Tuple[float, float]] = None
        self._path_tiles: List[Tuple[int, int]] = []
        self._path_index: int = 0
        self._idle_remaining: float = 0.0
        self._wander_count: int = 0
        
        super().__init__(entity, window, **config)
        
        # Config
        self.wander_radius = max(1.0, float(self.config.get("wander_radius", 5.0)))
        self.min_wander_distance = max(0.5, float(self.config.get("min_wander_distance", 2.0)))
        self.speed = max(0.0, float(self.config.get("speed", 40.0)))
        self.idle_time_min = max(0.0, float(self.config.get("idle_time_min", 1.0)))
        self.idle_time_max = max(self.idle_time_min, float(self.config.get("idle_time_max", 3.0)))
        self.anchor_to_spawn = bool(self.config.get("anchor_to_spawn", True))
        self.max_path_attempts = max(1, int(self.config.get("max_path_attempts", 5)))
        self._enabled = bool(self.config.get("enabled", True))
        
        # Get RNG stream
        self._rng = get_registry().get_rng_stream(WANDER_RNG_STREAM)
        
        # Set initial origin if anchoring to spawn
        if self.anchor_to_spawn:
            self._origin = (
                float(getattr(entity, "center_x", 0.0)),
                float(getattr(entity, "center_y", 0.0)),
            )
    
    @property
    def enabled(self) -> bool:
        """Whether wander is active."""
        return self._enabled
    
    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = bool(value)
    
    @property
    def state(self) -> str:
        """Current state: idle, wandering."""
        return self._state
    
    @property
    def is_wandering(self) -> bool:
        """Whether actively moving to a wander point."""
        return self._state == "wandering"
    
    @property
    def wander_count(self) -> int:
        """Number of completed wander moves."""
        return self._wander_count
    
    def _emit_event(self, event_type: str, **kwargs) -> None:
        """Emit a gameplay event."""
        my_id = getattr(self.entity, "mesh_id", "")
        
        payload = {
            "entity": my_id,
            "entity_name": getattr(self.entity, "mesh_name", ""),
            "wander_count": self._wander_count,
            **kwargs,
        }
        
        emit_gameplay_event(
            self.window,
            event_type,
            payload,
            source_entity_id=my_id,
            source_behaviour="Wander",
        )
    
    def _get_nav_grid(self) -> NavGrid | None:
        """Get the navigation grid from scene controller."""
        scene = getattr(self.window, "scene_controller", None)
        getter = getattr(scene, "get_nav_grid", None) if scene else None
        if callable(getter):
            return getter()
        return None
    
    def _get_origin(self) -> Tuple[float, float]:
        """Get the origin point for wander radius."""
        if self._origin is not None:
            return self._origin
        
        return (
            float(getattr(self.entity, "center_x", 0.0)),
            float(getattr(self.entity, "center_y", 0.0)),
        )
    
    def _pick_wander_point(self, grid: NavGrid) -> Optional[Tuple[float, float]]:
        """Pick a random walkable point within wander radius.
        
        Uses RNGService for deterministic selection.
        """
        origin = self._get_origin()
        ox, oy = origin
        tile_size = getattr(grid, "tile_size", 16)
        
        ex = float(getattr(self.entity, "center_x", 0.0))
        ey = float(getattr(self.entity, "center_y", 0.0))
        
        for _ in range(self.max_path_attempts):
            # Pick random angle and distance
            angle = self._rng.uniform(0.0, 2.0 * math.pi)
            dist_tiles = self._rng.uniform(self.min_wander_distance, self.wander_radius)
            dist_world = dist_tiles * tile_size
            
            # Calculate candidate point
            cx = ox + math.cos(angle) * dist_world
            cy = oy + math.sin(angle) * dist_world
            
            # Check if walkable
            tile = grid.world_to_tile(cx, cy)
            if not grid.is_walkable(*tile):
                continue
            
            # Check minimum distance from current position
            current_dist = math.hypot(cx - ex, cy - ey) / tile_size
            if current_dist < self.min_wander_distance * 0.5:
                continue
            
            return (cx, cy)
        
        return None
    
    def _compute_path(self, goal_world: Tuple[float, float], grid: NavGrid) -> bool:
        """Compute path to wander target."""
        self._path_tiles = []
        self._path_index = 0
        
        ex = float(getattr(self.entity, "center_x", 0.0))
        ey = float(getattr(self.entity, "center_y", 0.0))
        
        start_tile = grid.world_to_tile(ex, ey)
        goal_tile = grid.world_to_tile(goal_world[0], goal_world[1])
        
        if start_tile == goal_tile:
            self._path_tiles = [start_tile]
            return True
        
        path = astar(start_tile, goal_tile, grid, diag=False)
        if not path:
            return False
        
        # Remove start tile if present
        if path and path[0] == start_tile:
            path = path[1:]
        
        self._path_tiles = path
        return True
    
    def _start_idle(self) -> None:
        """Enter idle state with random duration."""
        self._state = "idle"
        self._idle_remaining = self._rng.uniform(self.idle_time_min, self.idle_time_max)
        self._wander_target = None
        self._path_tiles = []
        self._path_index = 0
    
    def _start_wander(self, grid: NavGrid) -> bool:
        """Start wandering to a new point."""
        target = self._pick_wander_point(grid)
        if target is None:
            return False
        
        if not self._compute_path(target, grid):
            return False
        
        self._state = "wandering"
        self._wander_target = target
        
        self._emit_event(
            "wander_started",
            target=target,
        )
        
        return True
    
    def _complete_wander(self) -> None:
        """Complete a wander move."""
        self._wander_count += 1
        
        self._emit_event(
            "wander_point_reached",
            position=(
                float(getattr(self.entity, "center_x", 0.0)),
                float(getattr(self.entity, "center_y", 0.0)),
            ),
        )
        
        self._start_idle()
    
    def start(self) -> None:
        """Start wandering."""
        grid = self._get_nav_grid()
        if grid is not None:
            if not self._start_wander(grid):
                self._start_idle()
    
    def stop(self) -> None:
        """Stop wandering."""
        if self._state != "idle":
            self._emit_event("wander_stopped")
        self._state = "idle"
        self._idle_remaining = 0.0
        self._wander_target = None
        self._path_tiles = []
        self._path_index = 0
    
    def update(self, dt: float) -> None:
        """Update wander state."""
        if dt <= 0:
            return
        if not self._enabled:
            return
        if self.speed <= 0:
            return
        
        grid = self._get_nav_grid()
        if grid is None:
            return
        
        # Update origin if not anchoring
        if not self.anchor_to_spawn and self._state == "idle":
            self._origin = (
                float(getattr(self.entity, "center_x", 0.0)),
                float(getattr(self.entity, "center_y", 0.0)),
            )
        
        # Handle idle state
        if self._state == "idle":
            self._idle_remaining -= dt
            if self._idle_remaining <= 0:
                if not self._start_wander(grid):
                    # Failed to find path, retry after short delay
                    self._idle_remaining = 0.5
            return
        
        # Wandering state
        if self._state != "wandering":
            return
        
        # Follow path
        if not self._path_tiles or self._path_index >= len(self._path_tiles):
            self._complete_wander()
            return
        
        # Get current and target positions
        ex = float(getattr(self.entity, "center_x", 0.0))
        ey = float(getattr(self.entity, "center_y", 0.0))
        
        waypoint_tile = self._path_tiles[self._path_index]
        wx, wy = grid.tile_center_world(waypoint_tile)
        
        # Check arrival at waypoint
        arrive_dist = max(2.0, getattr(grid, "tile_size", 16) / 4)
        dist = math.hypot(wx - ex, wy - ey)
        if dist <= arrive_dist:
            self._path_index += 1
            if self._path_index >= len(self._path_tiles):
                self._complete_wander()
            return
        
        # Move toward waypoint
        step = self.speed * dt
        if step >= dist:
            move_x = wx - ex
            move_y = wy - ey
        else:
            nx = (wx - ex) / dist
            ny = (wy - ey) / dist
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
    
    # =========================================================================
    # SaveableBehaviour Protocol
    # =========================================================================
    
    def saveable_state(self) -> Dict[str, Any]:
        """Return JSON-serializable state dict."""
        return {
            "_version": self.STATE_VERSION,
            "state": self._state,
            "origin": list(self._origin) if self._origin else None,
            "wander_target": list(self._wander_target) if self._wander_target else None,
            "path_tiles": [list(t) for t in self._path_tiles],
            "path_index": self._path_index,
            "idle_remaining": self._idle_remaining,
            "wander_count": self._wander_count,
        }
    
    def restore_state(self, state: Dict[str, Any]) -> None:
        """Apply previously saved state."""
        self._state = str(state.get("state", "idle"))
        
        origin = state.get("origin")
        if isinstance(origin, (list, tuple)) and len(origin) >= 2:
            self._origin = (float(origin[0]), float(origin[1]))
        
        wander_target = state.get("wander_target")
        if isinstance(wander_target, (list, tuple)) and len(wander_target) >= 2:
            self._wander_target = (float(wander_target[0]), float(wander_target[1]))
        else:
            self._wander_target = None
        
        path_tiles = state.get("path_tiles", [])
        self._path_tiles = []
        if isinstance(path_tiles, list):
            for t in path_tiles:
                if isinstance(t, (list, tuple)) and len(t) >= 2:
                    self._path_tiles.append((int(t[0]), int(t[1])))
        
        self._path_index = int(state.get("path_index", 0))
        self._idle_remaining = float(state.get("idle_remaining", 0.0))
        self._wander_count = int(state.get("wander_count", 0))
    
    # =========================================================================
    # Inspector Support
    # =========================================================================
    
    def get_inspector_state(self) -> Dict[str, Any]:
        """Return state for editor inspector."""
        return {
            "state": self._state,
            "origin": self._origin,
            "wander_target": self._wander_target,
            "path_length": len(self._path_tiles),
            "path_index": self._path_index,
            "idle_remaining": self._idle_remaining,
            "wander_count": self._wander_count,
            "wander_radius": self.wander_radius,
            "speed": self.speed,
        }


# =============================================================================
# Config Validation
# =============================================================================

def validate_wander_config(
    config: Dict[str, Any],
    *,
    entity_id: str = "",
) -> List[EventConfigError]:
    """Validate Wander configuration.
    
    Args:
        config: Configuration dictionary.
        entity_id: Entity ID for error reporting.
        
    Returns:
        List of validation errors.
    """
    errors: List[EventConfigError] = []
    behaviour_name = "Wander"
    
    # Validate numeric configs
    for field, min_val in [
        ("wander_radius", 0.0),
        ("min_wander_distance", 0.0),
        ("speed", 0.0),
        ("idle_time_min", 0.0),
        ("idle_time_max", 0.0),
    ]:
        value = config.get(field)
        if value is not None:
            try:
                val = float(value)
                if val < min_val:
                    errors.append(EventConfigError(
                        entity_id=entity_id,
                        behaviour_name=behaviour_name,
                        config_path=field,
                        message=f"{field} must be >= {min_val}",
                    ))
            except (TypeError, ValueError):
                errors.append(EventConfigError(
                    entity_id=entity_id,
                    behaviour_name=behaviour_name,
                    config_path=field,
                    message=f"{field} must be a number",
                ))
    
    # Validate idle_time_max >= idle_time_min
    idle_min = config.get("idle_time_min", 1.0)
    idle_max = config.get("idle_time_max", 3.0)
    try:
        if float(idle_max) < float(idle_min):
            errors.append(EventConfigError(
                entity_id=entity_id,
                behaviour_name=behaviour_name,
                config_path="idle_time_max",
                message="idle_time_max must be >= idle_time_min",
            ))
    except (TypeError, ValueError):
        pass
    
    return errors
