"""Blend of deterministic waypoint patrol + ChaseTarget pathfinding."""

from __future__ import annotations

import math
from typing import Any, cast

from ..pathfinding import NavGrid
from .base import Behaviour, ParamDef
from .chase_target import ChaseTargetBehaviour
from .registry import register_behaviour


@register_behaviour(
    "PatrolChase",
    description="Patrols between waypoints and switches to pathfinding chase when a target is acquired.",
    config_fields=[
        {
            "name": "patrol_points",
            "description": "List of {x,y} waypoints to visit",
            "type": "array",
            "default": [],
        },
        {
            "name": "patrol_tag",
            "description": "If set, discover waypoint entities by mesh_tag (sorted deterministically)",
            "type": "string",
            "default": "",
        },
        {
            "name": "patrol_speed",
            "description": "Movement speed while patrolling",
            "type": "float",
            "default": 80.0,
        },
        {
            "name": "chase_speed",
            "description": "Movement speed while chasing",
            "type": "float",
            "default": 90.0,
        },
        {
            "name": "acquire_radius_tiles",
            "description": "Acquire range in tiles",
            "type": "int",
            "default": 8,
        },
        {
            "name": "leash_radius_tiles",
            "description": "Stop chasing when target exceeds this range in tiles",
            "type": "int",
            "default": 12,
        },
        {
            "name": "stop_range_tiles",
            "description": "If within this range, stop moving but remain in chase state",
            "type": "int",
            "default": 0,
        },
        {
            "name": "give_up_ticks",
            "description": "If no_path persists this many ticks, disengage",
            "type": "int",
            "default": 30,
        },
        {
            "name": "cooldown_ticks",
            "description": "Ticks to stay idle after giving up",
            "type": "int",
            "default": 60,
        },
        {
            "name": "target_entity_id",
            "description": "Authored entity id to chase (matches mesh_entity_data.id)",
            "type": "string",
            "default": "",
        },
        {
            "name": "target_tag",
            "description": "Fallback: chase the nearest entity with this mesh_tag",
            "type": "string",
            "default": "",
        },
        {
            "name": "los_required",
            "description": "If true, require grid line-of-sight to acquire target",
            "type": "bool",
            "default": False,
        },
        {
            "name": "return_to_patrol",
            "description": "If true, return to patrol route after disengaging",
            "type": "bool",
            "default": True,
        },
        {
            "name": "resume_waypoint_mode",
            "description": "After returning, resume from nearest waypoint or continue to next",
            "type": "string",
            "default": "nearest",
        },
    ],
)
class PatrolChaseBehaviour(Behaviour):
    PARAM_DEFS = {
        "patrol_points": ParamDef(list, default=[], description="List of {x,y} waypoints to visit"),
        "patrol_tag": ParamDef(str, default="", description="Discover waypoints by mesh_tag"),
        "patrol_speed": ParamDef(float, default=80.0, description="Movement speed while patrolling"),
        "chase_speed": ParamDef(float, default=90.0, description="Movement speed while chasing"),
        "acquire_radius_tiles": ParamDef(int, default=8, description="Acquire range in tiles"),
        "leash_radius_tiles": ParamDef(int, default=12, description="Leash range in tiles"),
        "stop_range_tiles": ParamDef(int, default=0, description="Stop moving within this range"),
        "give_up_ticks": ParamDef(int, default=30, description="Ticks in no_path before disengage"),
        "cooldown_ticks": ParamDef(int, default=60, description="Ticks to stay idle after disengage"),
        "target_entity_id": ParamDef(str, default="", description="Authored entity id to chase"),
        "target_tag": ParamDef(str, default="", description="Fallback mesh_tag to chase"),
        "los_required": ParamDef(bool, default=False, description="Require grid LOS to acquire target"),
        "return_to_patrol": ParamDef(bool, default=True, description="Return to patrol after disengage"),
        "resume_waypoint_mode": ParamDef(str, default="nearest", description="nearest|next"),
    }

    def __init__(self, entity, window, **config: Any) -> None:
        super().__init__(entity, window, **config)
        self.state: str = "patrol"  # patrol|chase|return
        self._cooldown_remaining: int = 0

        self.patrol_speed = max(0.0, float(self.config.get("patrol_speed", 80.0)))
        self.chase_speed = max(0.0, float(self.config.get("chase_speed", 90.0)))
        self.acquire_radius_tiles = max(0, int(self.config.get("acquire_radius_tiles", 8) or 0))
        self.leash_radius_tiles = max(self.acquire_radius_tiles, int(self.config.get("leash_radius_tiles", 12) or 0))
        self.stop_range_tiles = max(0, int(self.config.get("stop_range_tiles", 0) or 0))
        self.give_up_ticks = max(1, int(self.config.get("give_up_ticks", 30) or 30))
        self.cooldown_ticks = max(0, int(self.config.get("cooldown_ticks", 60) or 0))
        self.target_entity_id = str(self.config.get("target_entity_id") or "").strip() or None
        self.target_tag = str(self.config.get("target_tag") or "").strip() or None
        self.los_required = bool(self.config.get("los_required", False))
        self.return_to_patrol = bool(self.config.get("return_to_patrol", True))
        mode = str(self.config.get("resume_waypoint_mode") or "nearest").strip().lower()
        self.resume_waypoint_mode = mode if mode in {"nearest", "next"} else "nearest"

        self._waypoints: list[tuple[float, float]] = self._coerce_points(self.config.get("patrol_points"))
        self._patrol_tag: str | None = str(self.config.get("patrol_tag") or "").strip() or None
        self._waypoints_built_from_tag: bool = False
        self._waypoint_index: int = 0

        self._chase: ChaseTargetBehaviour | None = None
        self._acquire_helper: ChaseTargetBehaviour | None = None
        self._return_goal_index: int | None = None

    @staticmethod
    def _coerce_points(raw: Any) -> list[tuple[float, float]]:
        points: list[tuple[float, float]] = []
        if not isinstance(raw, list):
            return points
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            try:
                points.append((float(entry["x"]), float(entry["y"])))
            except Exception:  # noqa: BLE001  # REASON: malformed authored waypoint entries should be skipped without breaking patrol setup
                continue
        return points

    @staticmethod
    def _entity_id(sprite: Any) -> str:
        payload = getattr(sprite, "mesh_entity_data", None)
        if isinstance(payload, dict):
            raw = payload.get("id") or payload.get("entity_id")
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
        raw = getattr(sprite, "mesh_name", None)
        return str(raw).strip() if raw is not None else ""

    def _iter_scene_sprites(self) -> list[Any]:
        scene = getattr(self.window, "scene_controller", None)
        getter = getattr(scene, "get_all_entities", None) if scene is not None else None
        if callable(getter):
            return list(getter())
        all_sprites = getattr(scene, "all_sprites", None) if scene is not None else None
        if all_sprites is None:
            return []
        return list(all_sprites)

    def _get_nav_grid(self) -> NavGrid | None:
        scene = getattr(self.window, "scene_controller", None)
        getter = getattr(scene, "get_nav_grid", None) if scene is not None else None
        if callable(getter):
            grid = getter()
            if isinstance(grid, NavGrid):
                return grid
            if (
                callable(getattr(grid, "world_to_tile", None))
                and callable(getattr(grid, "tile_to_world_center", None))
                and callable(getattr(grid, "find_path", None))
                and callable(getattr(grid, "has_line_of_sight", None))
                and callable(getattr(grid, "is_walkable", None))
            ):
                return cast(NavGrid, grid)
        return None

    def _ensure_waypoints(self) -> None:
        if self._waypoints:
            return
        if not self._patrol_tag or self._waypoints_built_from_tag:
            return
        candidates: list[tuple[float, float, str]] = []
        for sprite in self._iter_scene_sprites():
            if sprite is self.entity:
                continue
            tag = getattr(sprite, "mesh_tag", None)
            if str(tag or "").strip() != self._patrol_tag:
                continue
            try:
                x = float(getattr(sprite, "center_x"))
                y = float(getattr(sprite, "center_y"))
            except Exception:  # noqa: BLE001  # REASON: malformed tagged waypoint sprites should be skipped without breaking patrol discovery
                continue
            candidates.append((y, x, self._entity_id(sprite)))
        candidates.sort(key=lambda t: (t[0], t[1], t[2]))
        self._waypoints = [(x, y) for (y, x, _eid) in candidates]
        self._waypoints_built_from_tag = True

    def update(self, dt: float) -> None:
        if dt <= 0:
            return

        if self._cooldown_remaining > 0:
            self._cooldown_remaining = max(0, self._cooldown_remaining - 1)

        self._ensure_waypoints()
        if self.state == "chase":
            self._update_chase(dt)
            return
        if self.state == "return":
            self._update_return(dt)
            return
        self._update_patrol(dt)

    def _update_patrol(self, dt: float) -> None:
        if self._cooldown_remaining > 0:
            self._tick_patrol_motion(dt)
            return

        grid = self._get_nav_grid()
        if grid is None:
            self._tick_patrol_motion(dt)
            return

        # Attempt acquisition using the same ChaseTarget logic.
        # Reuse a single persistent helper for the pre-check scan so we do not
        # allocate a throwaway ChaseTargetBehaviour every idle patrol tick.
        # The helper is never .update()'d, so it stays in pristine post-__init__
        # state (state="idle", _cooldown_remaining=0) permanently — no
        # cooldown/disengage contamination (this is what makes Option A safe).
        if self._acquire_helper is None:
            self._acquire_helper = self._build_chase()  # built once, reused
        target = self._acquire_helper._acquire_target(grid)  # noqa: SLF001
        if target is not None:
            self.state = "chase"
            self._chase = self._build_chase()  # fresh chaser promoted, pristine idle
            self._chase.update(dt)
            return

        self._tick_patrol_motion(dt)

    def _update_chase(self, dt: float) -> None:
        chase = self._chase
        if chase is None:
            self.state = "patrol"
            return
        chase.update(dt)
        if chase.state == "chase":
            return

        # Disengaged or cooling down: return to patrol route (optional).
        if chase.state == "cooldown":
            self._cooldown_remaining = max(self._cooldown_remaining, int(self.cooldown_ticks))

        self._chase = None
        if not self.return_to_patrol:
            self.state = "patrol"
            return

        self._return_goal_index = self._pick_return_goal_index()
        if self._return_goal_index is None:
            self.state = "patrol"
            return
        self.state = "return"

    def _update_return(self, dt: float) -> None:
        goal_idx = self._return_goal_index
        if goal_idx is None or goal_idx < 0 or goal_idx >= len(self._waypoints):
            self.state = "patrol"
            self._return_goal_index = None
            return

        goal_x, goal_y = self._waypoints[goal_idx]
        if self._move_toward_world(goal_x, goal_y, speed=self.patrol_speed, dt=dt, arrive_dist=2.0):
            # Snap and resume patrol.
            self._waypoint_index = goal_idx
            self.state = "patrol"
            self._return_goal_index = None

    def _pick_return_goal_index(self) -> int | None:
        if len(self._waypoints) < 1:
            return None
        if self.resume_waypoint_mode == "next":
            return max(0, min(int(self._waypoint_index), len(self._waypoints) - 1))

        ex = float(getattr(self.entity, "center_x", 0.0))
        ey = float(getattr(self.entity, "center_y", 0.0))
        best_idx = 0
        best_dist: float | None = None
        for idx, (x, y) in enumerate(self._waypoints):
            dist = (x - ex) ** 2 + (y - ey) ** 2
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best_idx = idx
        return best_idx

    def _tick_patrol_motion(self, dt: float) -> None:
        if len(self._waypoints) < 2:
            return
        idx = int(self._waypoint_index) % len(self._waypoints)
        x, y = self._waypoints[idx]
        reached = self._move_toward_world(x, y, speed=self.patrol_speed, dt=dt, arrive_dist=2.0)
        if reached:
            self._waypoint_index = (idx + 1) % len(self._waypoints)

    def _move_toward_world(self, goal_x: float, goal_y: float, *, speed: float, dt: float, arrive_dist: float) -> bool:
        ex = float(getattr(self.entity, "center_x", 0.0))
        ey = float(getattr(self.entity, "center_y", 0.0))
        dx = float(goal_x) - ex
        dy = float(goal_y) - ey
        dist = math.hypot(dx, dy)
        if dist <= max(0.0, float(arrive_dist)):
            return True
        if speed <= 0:
            return False
        step = float(speed) * float(dt)
        if step <= 0:
            return False
        if step >= dist:
            self.entity.center_x = float(goal_x)
            self.entity.center_y = float(goal_y)
            return True
        nx = dx / dist
        ny = dy / dist
        move_x = nx * step
        move_y = ny * step
        mover = getattr(self.window, "move_entity_with_collision", None)
        if callable(mover):
            mover(self.entity, move_x, move_y)
        else:
            self.entity.center_x = ex + move_x
            self.entity.center_y = ey + move_y
        return False

    def _build_chase(self) -> ChaseTargetBehaviour:
        return ChaseTargetBehaviour(
            self.entity,
            self.window,
            target_entity_id=self.target_entity_id or "",
            target_tag=self.target_tag or "",
            acquire_radius_tiles=int(self.acquire_radius_tiles),
            leash_radius_tiles=int(self.leash_radius_tiles),
            stop_range_tiles=int(self.stop_range_tiles),
            speed=float(self.chase_speed),
            give_up_ticks=int(self.give_up_ticks),
            cooldown_ticks=int(self.cooldown_ticks),
            los_required=bool(self.los_required),
            repath_min_ticks=2,
            no_path_repath_ticks=10,
        )
