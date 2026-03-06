"""FleeFromTarget behaviour - deterministic threat avoidance.

Detects nearby threats and moves to a safe point away from them using
pathfinding. Uses RNGService for deterministic flee point selection.

Events emitted:
- flee_started: When fleeing begins
- flee_completed: When reached a safe distance
- flee_failed: When no valid flee path could be found

Save/restore:
- Tracks threat ID, flee target point, current path state
- Fully deterministic on restore
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, cast

from ..event_emit import emit_gameplay_event
from ..gameplay_event_bus import EventConfigError
from ..pathfinding import NavGrid, astar
from ..singletons import get_registry
from .base import Behaviour, ParamDef
from .registry import register_behaviour


# =============================================================================
# Constants
# =============================================================================

# Number of candidate flee points to evaluate
FLEE_CANDIDATES = 8

# RNG stream name for deterministic flee point selection
FLEE_RNG_STREAM = "ai_flee"


# =============================================================================
# FleeFromTarget Behaviour
# =============================================================================

@register_behaviour(
    "FleeFromTarget",
    description="Flees from nearby threats to a safe distance.",
    config_fields=[
        {
            "name": "threat_tags",
            "description": "Tags that identify threat entities",
            "type": "array",
            "default": [],
        },
        {
            "name": "threat_entity_id",
            "description": "Specific entity ID to flee from (overrides tags)",
            "type": "string",
            "default": "",
        },
        {
            "name": "detection_radius",
            "description": "Radius in tiles to detect threats",
            "type": "float",
            "default": 6.0,
        },
        {
            "name": "flee_distance",
            "description": "Distance in tiles to flee from threat",
            "type": "float",
            "default": 10.0,
        },
        {
            "name": "safe_distance",
            "description": "Distance at which fleeing completes successfully",
            "type": "float",
            "default": 8.0,
        },
        {
            "name": "speed",
            "description": "Movement speed while fleeing",
            "type": "float",
            "default": 100.0,
        },
        {
            "name": "repath_interval_ticks",
            "description": "Ticks between path recalculation while fleeing",
            "type": "int",
            "default": 10,
        },
        {
            "name": "max_flee_ticks",
            "description": "Maximum ticks to flee before giving up",
            "type": "int",
            "default": 300,
        },
        {
            "name": "cooldown_ticks",
            "description": "Ticks to wait after completing a flee",
            "type": "int",
            "default": 30,
        },
        {
            "name": "enabled",
            "description": "Whether flee behaviour is active",
            "type": "bool",
            "default": True,
        },
    ],
)
class FleeFromTargetBehaviour(Behaviour):
    """Flees from threats to a safe distance.
    
    Implements SaveableBehaviour for deterministic save/restore.
    Uses RNGService for deterministic flee point selection.
    """
    
    STATE_VERSION = 1
    
    PARAM_DEFS = {
        "threat_tags": ParamDef(list, [], "Tags identifying threats"),
        "threat_entity_id": ParamDef(str, "", "Specific entity to flee from"),
        "detection_radius": ParamDef(float, 6.0, "Detection range in tiles"),
        "flee_distance": ParamDef(float, 10.0, "Distance to flee"),
        "safe_distance": ParamDef(float, 8.0, "Safe distance threshold"),
        "speed": ParamDef(float, 100.0, "Flee movement speed"),
        "repath_interval_ticks": ParamDef(int, 10, "Ticks between repath"),
        "max_flee_ticks": ParamDef(int, 300, "Maximum flee duration"),
        "cooldown_ticks": ParamDef(int, 30, "Cooldown after flee"),
        "enabled": ParamDef(bool, True, "Whether active"),
    }

    def __init__(self, entity, window, **config: Any) -> None:
        # Initialize private state before super().__init__
        self._enabled: bool = True
        self._state: str = "idle"  # idle|fleeing|cooldown
        self._threat = None
        self._threat_id: Optional[str] = None
        self._flee_target: Optional[Tuple[float, float]] = None
        self._path_tiles: List[Tuple[int, int]] = []
        self._path_index: int = 0
        self._ticks_since_repath: int = 0
        self._flee_ticks: int = 0
        self._cooldown_remaining: int = 0
        
        super().__init__(entity, window, **config)
        
        # Config
        self.threat_tags: Set[str] = set(
            str(t) for t in (self.config.get("threat_tags") or []) if t
        )
        self.threat_entity_id = str(self.config.get("threat_entity_id", "")).strip()
        self.detection_radius = max(1.0, float(self.config.get("detection_radius", 6.0)))
        self.flee_distance = max(1.0, float(self.config.get("flee_distance", 10.0)))
        self.safe_distance = max(1.0, float(self.config.get("safe_distance", 8.0)))
        self.speed = max(0.0, float(self.config.get("speed", 100.0)))
        self.repath_interval_ticks = max(1, int(self.config.get("repath_interval_ticks", 10)))
        self.max_flee_ticks = max(1, int(self.config.get("max_flee_ticks", 300)))
        self.cooldown_ticks = max(0, int(self.config.get("cooldown_ticks", 30)))
        self._enabled = bool(self.config.get("enabled", True))
        
        # Get RNG stream
        self._rng = get_registry().get_rng_stream(FLEE_RNG_STREAM)
    
    @property
    def enabled(self) -> bool:
        """Whether flee behaviour is active."""
        return self._enabled
    
    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = bool(value)
    
    @property
    def state(self) -> str:
        """Current state: idle, fleeing, cooldown."""
        return self._state
    
    @property
    def is_fleeing(self) -> bool:
        """Whether actively fleeing."""
        return self._state == "fleeing"
    
    @property
    def current_threat_id(self) -> Optional[str]:
        """ID of current threat, if any."""
        return self._threat_id
    
    def _emit_event(self, event_type: str, **kwargs) -> None:
        """Emit a gameplay event."""
        my_id = getattr(self.entity, "mesh_id", "")
        
        payload = {
            "entity": my_id,
            "entity_name": getattr(self.entity, "mesh_name", ""),
            "threat_id": self._threat_id or "",
            "state": self._state,
            **kwargs,
        }
        
        emit_gameplay_event(
            self.window,
            event_type,
            payload,
            source_entity_id=my_id,
            source_behaviour="FleeFromTarget",
        )
    
    def _get_nav_grid(self) -> NavGrid | None:
        """Get the navigation grid from scene controller."""
        scene = getattr(self.window, "scene_controller", None)
        getter = getattr(scene, "get_nav_grid", None) if scene else None
        if callable(getter):
            result = getter()
            return cast(NavGrid, result) if result is not None else None
        return None
    
    @staticmethod
    def _entity_id(sprite: Any) -> str:
        """Get deterministic ID for an entity."""
        payload = getattr(sprite, "mesh_entity_data", None)
        if isinstance(payload, dict):
            raw = payload.get("id") or payload.get("entity_id")
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
        raw = getattr(sprite, "mesh_id", None) or getattr(sprite, "mesh_name", None)
        return str(raw).strip() if raw else ""
    
    def _iter_candidates(self) -> List[Any]:
        """Get all candidate sprites in the scene."""
        scene = getattr(self.window, "scene_controller", None)
        if scene is None:
            return []
        
        getter = getattr(scene, "get_all_entities", None)
        if callable(getter):
            result = getter()
            return list(result) if isinstance(result, Iterable) else []
        
        sprites = getattr(scene, "all_sprites", None)
        return list(sprites) if sprites else []
    
    def _resolve_threat_by_id(self, entity_id: str) -> Any | None:
        """Find a specific entity by ID."""
        scene = getattr(self.window, "scene_controller", None)
        if scene is None:
            return None
        
        # Try scene index
        idx = getattr(scene, "_scene_index", None)
        if idx is not None:
            getter = getattr(idx, "get_by_id", None)
            if callable(getter):
                return getter(entity_id)
        
        # Fallback
        for sprite in self._iter_candidates():
            if self._entity_id(sprite) == entity_id:
                return sprite
        return None
    
    def _distance_tiles_to(self, sprite: Any, grid: NavGrid) -> float:
        """Calculate tile distance to a sprite."""
        sx, sy = grid.world_to_tile(
            float(getattr(self.entity, "center_x", 0.0)),
            float(getattr(self.entity, "center_y", 0.0)),
        )
        tx, ty = grid.world_to_tile(
            float(getattr(sprite, "center_x", 0.0)),
            float(getattr(sprite, "center_y", 0.0)),
        )
        return math.hypot(tx - sx, ty - sy)
    
    def _detect_threat(self, grid: NavGrid) -> Any | None:
        """Detect the nearest threat within detection radius."""
        # Check specific threat first
        if self.threat_entity_id:
            threat = self._resolve_threat_by_id(self.threat_entity_id)
            if threat is not None:
                dist = self._distance_tiles_to(threat, grid)
                if dist <= self.detection_radius:
                    return threat
            return None
        
        # Check by tags
        if not self.threat_tags:
            return None
        
        best = None
        best_dist: Optional[float] = None
        best_id = ""
        
        for sprite in self._iter_candidates():
            if sprite is self.entity:
                continue
            
            # Check tags
            sprite_tags = set(getattr(sprite, "mesh_tags", []) or [])
            if not (sprite_tags & self.threat_tags):
                continue
            
            dist = self._distance_tiles_to(sprite, grid)
            if dist > self.detection_radius:
                continue
            
            eid = self._entity_id(sprite)
            
            # Deterministic selection: closest, then by ID
            if best is None or (best_dist is not None and dist < best_dist) or \
               (best_dist is not None and dist == best_dist and eid < best_id):
                best = sprite
                best_dist = dist
                best_id = eid
        
        return best
    
    def _calculate_flee_point(self, threat: Any, grid: NavGrid) -> Optional[Tuple[float, float]]:
        """Calculate a point to flee toward.
        
        Uses deterministic RNG to select from candidate points.
        """
        # Get positions
        ex = float(getattr(self.entity, "center_x", 0.0))
        ey = float(getattr(self.entity, "center_y", 0.0))
        tx = float(getattr(threat, "center_x", 0.0))
        ty = float(getattr(threat, "center_y", 0.0))
        
        # Direction away from threat
        dx = ex - tx
        dy = ey - ty
        dist = math.hypot(dx, dy)
        if dist < 0.001:
            # Directly on top, pick random direction
            angle = self._rng.uniform(0.0, 2.0 * math.pi)
            dx = math.cos(angle)
            dy = math.sin(angle)
        else:
            dx /= dist
            dy /= dist
        
        # Get tile size
        tile_size = getattr(grid, "tile_size", 16)
        
        # Generate candidate points in the flee direction
        flee_world_dist = self.flee_distance * tile_size
        
        candidates: List[Tuple[float, float, float]] = []  # (x, y, score)
        
        for i in range(FLEE_CANDIDATES):
            # Spread candidates in a cone away from threat
            angle_offset = (i - FLEE_CANDIDATES // 2) * (math.pi / 8)
            cos_a = math.cos(angle_offset)
            sin_a = math.sin(angle_offset)
            
            # Rotate the flee direction
            rx = dx * cos_a - dy * sin_a
            ry = dx * sin_a + dy * cos_a
            
            # Calculate candidate world position
            cx = ex + rx * flee_world_dist
            cy = ey + ry * flee_world_dist
            
            # Check if tile is walkable
            tile = grid.world_to_tile(cx, cy)
            if grid.is_walkable(tile):
                # Score by distance from threat
                threat_dist = math.hypot(cx - tx, cy - ty)
                candidates.append((cx, cy, threat_dist))
        
        if not candidates:
            return None
        
        # Sort by score (distance from threat) - deterministic
        candidates.sort(key=lambda c: (-c[2], c[0], c[1]))
        
        # Pick from top candidates with some randomness for variety
        top_n = min(3, len(candidates))
        idx = self._rng.randint(0, top_n - 1)
        return (candidates[idx][0], candidates[idx][1])
    
    def _compute_path(self, goal_world: Tuple[float, float], grid: NavGrid) -> bool:
        """Compute path to flee target."""
        self._path_tiles = []
        self._path_index = 0
        self._ticks_since_repath = 0
        
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
    
    def _start_flee(self, threat: Any, grid: NavGrid) -> bool:
        """Start fleeing from a threat."""
        flee_point = self._calculate_flee_point(threat, grid)
        if flee_point is None:
            return False
        
        if not self._compute_path(flee_point, grid):
            return False
        
        self._state = "fleeing"
        self._threat = threat
        self._threat_id = self._entity_id(threat)
        self._flee_target = flee_point
        self._flee_ticks = 0
        
        self._emit_event(
            "flee_started",
            threat_name=getattr(threat, "mesh_name", ""),
            flee_target=flee_point,
        )
        
        return True
    
    def _complete_flee(self, reason: str = "safe_distance") -> None:
        """Complete fleeing successfully."""
        self._emit_event(
            "flee_completed",
            reason=reason,
            flee_ticks=self._flee_ticks,
        )
        
        self._state = "cooldown"
        self._cooldown_remaining = self.cooldown_ticks
        self._threat = None
        self._threat_id = None
        self._flee_target = None
        self._path_tiles = []
        self._path_index = 0
    
    def _fail_flee(self, reason: str = "no_path") -> None:
        """Fail fleeing."""
        self._emit_event(
            "flee_failed",
            reason=reason,
            flee_ticks=self._flee_ticks,
        )
        
        self._state = "cooldown"
        self._cooldown_remaining = self.cooldown_ticks
        self._threat = None
        self._threat_id = None
        self._flee_target = None
        self._path_tiles = []
        self._path_index = 0
    
    def update(self, dt: float) -> None:
        """Update flee state."""
        if dt <= 0:
            return
        if not self._enabled:
            return
        if self.speed <= 0:
            return
        
        grid = self._get_nav_grid()
        if grid is None:
            return
        
        # Handle cooldown
        if self._state == "cooldown":
            self._cooldown_remaining = max(0, self._cooldown_remaining - 1)
            if self._cooldown_remaining <= 0:
                self._state = "idle"
            return
        
        # Idle: detect threats
        if self._state == "idle":
            threat = self._detect_threat(grid)
            if threat is not None:
                if not self._start_flee(threat, grid):
                    self._fail_flee("no_valid_flee_point")
            return
        
        # Fleeing
        if self._state != "fleeing":
            return
        
        self._flee_ticks += 1
        self._ticks_since_repath += 1
        
        # Check max flee time
        if self._flee_ticks > self.max_flee_ticks:
            self._fail_flee("timeout")
            return
        
        # Check if threat still exists and is nearby
        if self._threat is None or self._threat_id is None:
            self._complete_flee("threat_gone")
            return
        
        # Re-check threat distance
        dist_to_threat = self._distance_tiles_to(self._threat, grid)
        if dist_to_threat >= self.safe_distance:
            self._complete_flee("safe_distance")
            return
        
        # Repath if needed
        if self._ticks_since_repath >= self.repath_interval_ticks:
            flee_point = self._calculate_flee_point(self._threat, grid)
            if flee_point is not None:
                self._flee_target = flee_point
                self._compute_path(flee_point, grid)
        
        # Follow path
        if not self._path_tiles or self._path_index >= len(self._path_tiles):
            # Path exhausted, try to repath
            if self._flee_target:
                if not self._compute_path(self._flee_target, grid):
                    self._fail_flee("no_path")
                    return
            else:
                self._fail_flee("no_target")
                return
        
        if self._path_index >= len(self._path_tiles):
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
            "threat_id": self._threat_id,
            "flee_target": list(self._flee_target) if self._flee_target else None,
            "path_tiles": [list(t) for t in self._path_tiles],
            "path_index": self._path_index,
            "ticks_since_repath": self._ticks_since_repath,
            "flee_ticks": self._flee_ticks,
            "cooldown_remaining": self._cooldown_remaining,
        }
    
    def restore_state(self, state: Dict[str, Any]) -> None:
        """Apply previously saved state."""
        self._state = str(state.get("state", "idle"))
        self._threat_id = state.get("threat_id")
        
        flee_target = state.get("flee_target")
        if isinstance(flee_target, (list, tuple)) and len(flee_target) >= 2:
            self._flee_target = (float(flee_target[0]), float(flee_target[1]))
        else:
            self._flee_target = None
        
        path_tiles = state.get("path_tiles", [])
        self._path_tiles = []
        if isinstance(path_tiles, list):
            for t in path_tiles:
                if isinstance(t, (list, tuple)) and len(t) >= 2:
                    self._path_tiles.append((int(t[0]), int(t[1])))
        
        self._path_index = int(state.get("path_index", 0))
        self._ticks_since_repath = int(state.get("ticks_since_repath", 0))
        self._flee_ticks = int(state.get("flee_ticks", 0))
        self._cooldown_remaining = int(state.get("cooldown_remaining", 0))
        
        # Re-acquire threat if fleeing
        if self._state == "fleeing" and self._threat_id:
            self._threat = self._resolve_threat_by_id(self._threat_id)
            if self._threat is None:
                # Threat gone, complete flee
                self._state = "idle"
                self._threat_id = None
        else:
            self._threat = None
    
    # =========================================================================
    # Inspector Support
    # =========================================================================
    
    def get_inspector_state(self) -> Dict[str, Any]:
        """Return state for editor inspector."""
        threat_pos = None
        if self._threat is not None:
            threat_pos = (
                float(getattr(self._threat, "center_x", 0.0)),
                float(getattr(self._threat, "center_y", 0.0)),
            )
        
        return {
            "state": self._state,
            "threat_id": self._threat_id,
            "threat_position": threat_pos,
            "flee_target": self._flee_target,
            "flee_ticks": self._flee_ticks,
            "path_length": len(self._path_tiles),
            "path_index": self._path_index,
            "cooldown_remaining": self._cooldown_remaining,
            "detection_radius": self.detection_radius,
            "flee_distance": self.flee_distance,
            "safe_distance": self.safe_distance,
            "speed": self.speed,
        }


# =============================================================================
# Config Validation
# =============================================================================

def validate_flee_from_target_config(
    config: Dict[str, Any],
    *,
    entity_id: str = "",
) -> List[EventConfigError]:
    """Validate FleeFromTarget configuration.
    
    Args:
        config: Configuration dictionary.
        entity_id: Entity ID for error reporting.
        
    Returns:
        List of validation errors.
    """
    errors: List[EventConfigError] = []
    behaviour_name = "FleeFromTarget"
    
    # Validate threat_tags or threat_entity_id
    threat_tags = config.get("threat_tags", [])
    threat_entity_id = config.get("threat_entity_id", "")
    
    if not threat_tags and not threat_entity_id:
        errors.append(EventConfigError(
            entity_id=entity_id,
            behaviour_name=behaviour_name,
            config_path="threat_tags",
            message="either threat_tags or threat_entity_id must be specified",
        ))
    
    # Validate numeric configs
    for field, min_val in [
        ("detection_radius", 0.0),
        ("flee_distance", 0.0),
        ("safe_distance", 0.0),
        ("speed", 0.0),
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
    
    return errors
