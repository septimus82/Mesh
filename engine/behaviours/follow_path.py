"""Behaviour that follows an A* path on the active tile collision grid."""

from __future__ import annotations

import math
from typing import Any, cast

from ..pathfinding import NavGrid, astar
from .base import Behaviour, ParamDef
from .registry import register_behaviour


@register_behaviour(
    "FollowPath",
    description="Moves toward a target using A* pathfinding over the tile collision grid.",
    config_fields=[
        {
            "name": "target_name",
            "description": "Name of the sprite to pathfind toward (uses find_sprite_by_name)",
            "type": "string",
            "default": "",
        },
        {
            "name": "goal_x",
            "description": "Optional goal X world coordinate (used if target_name is empty)",
            "type": "float",
            "default": None,
        },
        {
            "name": "goal_y",
            "description": "Optional goal Y world coordinate (used if target_name is empty)",
            "type": "float",
            "default": None,
        },
        {
            "name": "speed",
            "description": "Movement speed in units per second",
            "type": "float",
            "default": 80.0,
        },
        {
            "name": "arrive_dist",
            "description": "Distance threshold to consider the goal reached",
            "type": "float",
            "default": 4.0,
        },
        {
            "name": "repath_interval",
            "description": "Seconds between path recomputation",
            "type": "float",
            "default": 0.25,
        },
        {
            "name": "repath_min_ticks",
            "description": "Minimum update() ticks between path recomputation (deterministic throttle)",
            "type": "int",
            "default": 2,
        },
        {
            "name": "no_path_repath_ticks",
            "description": "Ticks to wait before retrying when no path exists",
            "type": "int",
            "default": 10,
        },
        {
            "name": "diag",
            "description": "If true, allow diagonal movement in A*",
            "type": "bool",
            "default": False,
        },
    ],
)
class FollowPathBehaviour(Behaviour):
    PARAM_DEFS = {
        "target_name": ParamDef(str, default="", description="Sprite name to pathfind toward"),
        "goal_x": ParamDef(float, default=None, description="Goal X world coordinate"),
        "goal_y": ParamDef(float, default=None, description="Goal Y world coordinate"),
        "speed": ParamDef(float, default=80.0, description="Movement speed in units per second"),
        "arrive_dist": ParamDef(float, default=4.0, description="Goal distance threshold"),
        "repath_interval": ParamDef(float, default=0.25, description="Seconds between path recomputation"),
        "repath_min_ticks": ParamDef(int, default=2, description="Minimum ticks between path recomputation"),
        "no_path_repath_ticks": ParamDef(int, default=10, description="Ticks to wait before retrying when no path exists"),
        "diag": ParamDef(bool, default=False, description="Allow diagonal movement"),
    }

    def __init__(self, entity, window, **config) -> None:
        super().__init__(entity, window, **config)
        self.target_name: str | None = str(self.config.get("target_name") or "").strip() or None
        self.goal_x = self._coerce_float(self.config.get("goal_x"))
        self.goal_y = self._coerce_float(self.config.get("goal_y"))
        self.speed = float(self.config.get("speed", 80.0))
        self.arrive_dist = max(0.0, float(self.config.get("arrive_dist", 4.0)))
        self.repath_interval = max(0.0, float(self.config.get("repath_interval", 0.25)))
        self.repath_min_ticks = max(1, int(self.config.get("repath_min_ticks", 2) or 2))
        self.no_path_repath_ticks = max(1, int(self.config.get("no_path_repath_ticks", 10) or 10))
        self.diag = bool(self.config.get("diag", False))

        self.state: str = "idle"
        self.repath_count: int = 0
        self._repath_timer = 0.0
        self._ticks_since_repath: int = 999999
        self._last_goal_tile: tuple[int, int] | None = None
        self._pending_goal_tile: tuple[int, int] | None = None
        self._pending_goal_ticks: int = 0
        self._path_tiles: list[tuple[int, int]] = []
        self._path_index: int = 0

    @staticmethod
    def _coerce_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except Exception:  # noqa: BLE001  # REASON: invalid authored goal coordinates should fall back to None without breaking behaviour init
            return None

    def update(self, dt: float) -> None:
        if dt <= 0:
            return
        if self.speed <= 0:
            return

        goal = self._resolve_goal_world()
        if goal is None:
            return

        gx, gy = goal
        self._ticks_since_repath += 1
        dx0 = gx - float(getattr(self.entity, "center_x", 0.0))
        dy0 = gy - float(getattr(self.entity, "center_y", 0.0))
        if math.hypot(dx0, dy0) <= self.arrive_dist:
            self.state = "idle"
            return

        self._repath_timer = max(0.0, self._repath_timer - dt)
        grid = self._get_nav_grid()
        if grid is None:
            return
        goal_tile = grid.world_to_tile(gx, gy)
        if self._last_goal_tile is None:
            self._last_goal_tile = goal_tile
            self._pending_goal_tile = None
            self._pending_goal_ticks = 0
        elif goal_tile != self._last_goal_tile:
            self._last_goal_tile = goal_tile
            self._pending_goal_tile = goal_tile
            self._pending_goal_ticks = 0
        if self._pending_goal_tile is not None:
            self._pending_goal_ticks += 1
        goal_change_ready = self._pending_goal_tile is not None and self._pending_goal_ticks >= self.repath_min_ticks

        should_repath = False
        if goal_change_ready:
            should_repath = True
        if not self._path_tiles or self._path_index >= len(self._path_tiles):
            should_repath = True
        if self.repath_interval > 0.0 and self._repath_timer <= 0.0 and self._ticks_since_repath >= self.repath_min_ticks:
            should_repath = True

        if self.state == "no_path" and not goal_change_ready and self._ticks_since_repath < self.no_path_repath_ticks:
            should_repath = False

        if should_repath and self._ticks_since_repath >= self.repath_min_ticks:
            self._compute_path_to(goal, grid=grid)
            self._pending_goal_tile = None
            self._pending_goal_ticks = 0

        if self.state == "no_path":
            return
        if not self._path_tiles or self._path_index >= len(self._path_tiles):
            return

        waypoint_tile = self._path_tiles[self._path_index]
        if waypoint_tile == goal_tile and self._path_index == len(self._path_tiles) - 1:
            wx, wy = (gx, gy)
        else:
            wx, wy = grid.tile_center_world(waypoint_tile)

        ex = float(getattr(self.entity, "center_x", 0.0))
        ey = float(getattr(self.entity, "center_y", 0.0))
        dx = wx - ex
        dy = wy - ey
        dist = math.hypot(dx, dy)
        if dist <= max(self.arrive_dist, 1.0):
            self._path_index += 1
            return

        step = self.speed * dt
        if step <= 0:
            return
        nx = dx / dist
        ny = dy / dist

        move_x = nx * min(step, dist)
        move_y = ny * min(step, dist)

        scene = getattr(self.window, "scene_controller", None)
        mover = getattr(scene, "move_entity_with_collision", None) if scene is not None else None
        if callable(mover):
            mover(self.entity, move_x, move_y)
        else:
            self.entity.center_x = ex + move_x
            self.entity.center_y = ey + move_y

    def _get_nav_grid(self) -> NavGrid | None:
        scene = getattr(self.window, "scene_controller", None)
        getter = getattr(scene, "get_nav_grid", None) if scene is not None else None
        if callable(getter):
            grid = getter()
            if isinstance(grid, NavGrid):
                return grid
            if (
                callable(getattr(grid, "world_to_tile", None))
                and callable(getattr(grid, "tile_center_world", None))
            ):
                return cast(NavGrid, grid)
        return None

    def _resolve_goal_world(self) -> tuple[float, float] | None:
        if self.target_name:
            finder = getattr(self.window, "find_sprite_by_name", None)
            if callable(finder):
                target = finder(self.target_name)
                if target is not None:
                    return (float(getattr(target, "center_x", 0.0)), float(getattr(target, "center_y", 0.0)))

        if self.goal_x is None or self.goal_y is None:
            return None
        return (float(self.goal_x), float(self.goal_y))

    def _compute_path_to(self, goal_world: tuple[float, float], *, grid: NavGrid) -> None:
        self._path_tiles = []
        self._path_index = 0
        self.repath_count += 1
        self._ticks_since_repath = 0

        start_tile = grid.world_to_tile(float(getattr(self.entity, "center_x", 0.0)), float(getattr(self.entity, "center_y", 0.0)))
        goal_tile = grid.world_to_tile(goal_world[0], goal_world[1])
        if start_tile == goal_tile:
            self._path_tiles = [start_tile]
            self._path_index = 0
            self._repath_timer = self.repath_interval
            self.state = "following"
            return
        path = astar(start_tile, goal_tile, grid, diag=self.diag)
        if not path:
            self.state = "no_path"
            return

        # Drop current tile if present.
        if path and path[0] == start_tile:
            path = path[1:]
        self._path_tiles = path
        self._path_index = 0
        self._repath_timer = self.repath_interval
        self.state = "following"
