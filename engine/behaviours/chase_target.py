"""Deterministic chase behaviour built on FollowPath + tile-grid nav."""

from __future__ import annotations

import math
from typing import Any

from ..pathfinding import NavGrid, line_of_sight_clear
from .base import Behaviour, ParamDef
from .follow_path import FollowPathBehaviour
from .registry import register_behaviour


@register_behaviour(
    "ChaseTarget",
    description="Acquires a nearby target and chases it using grid-based pathfinding.",
    config_fields=[
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
            "name": "speed",
            "description": "Chase movement speed",
            "type": "float",
            "default": 90.0,
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
            "name": "los_required",
            "description": "If true, require grid line-of-sight to acquire target",
            "type": "bool",
            "default": False,
        },
        {
            "name": "repath_min_ticks",
            "description": "Forwarded to FollowPath (deterministic throttle)",
            "type": "int",
            "default": 2,
        },
        {
            "name": "no_path_repath_ticks",
            "description": "Forwarded to FollowPath",
            "type": "int",
            "default": 10,
        },
    ],
)
class ChaseTargetBehaviour(Behaviour):
    PARAM_DEFS = {
        "target_entity_id": ParamDef(str, default="", description="Authored entity id to chase"),
        "target_tag": ParamDef(str, default="", description="Fallback mesh_tag to chase"),
        "acquire_radius_tiles": ParamDef(int, default=8, description="Acquire range in tiles"),
        "leash_radius_tiles": ParamDef(int, default=12, description="Leash range in tiles"),
        "stop_range_tiles": ParamDef(int, default=0, description="Stop moving within this range"),
        "speed": ParamDef(float, default=90.0, description="Chase movement speed"),
        "give_up_ticks": ParamDef(int, default=30, description="Ticks in no_path before disengage"),
        "cooldown_ticks": ParamDef(int, default=60, description="Ticks to stay idle after disengage"),
        "los_required": ParamDef(bool, default=False, description="Require grid LOS to acquire target"),
        "repath_min_ticks": ParamDef(int, default=2, description="Forwarded to FollowPath"),
        "no_path_repath_ticks": ParamDef(int, default=10, description="Forwarded to FollowPath"),
    }

    def __init__(self, entity, window, **config: Any) -> None:
        super().__init__(entity, window, **config)
        self.target_entity_id = str(self.config.get("target_entity_id") or "").strip() or None
        self.target_tag = str(self.config.get("target_tag") or "").strip() or None
        self.acquire_radius_tiles = max(0, int(self.config.get("acquire_radius_tiles", 8) or 0))
        self.leash_radius_tiles = max(self.acquire_radius_tiles, int(self.config.get("leash_radius_tiles", 12) or 0))
        self.stop_range_tiles = max(0, int(self.config.get("stop_range_tiles", 0) or 0))
        self.speed = float(self.config.get("speed", 90.0))
        self.give_up_ticks = max(1, int(self.config.get("give_up_ticks", 30) or 30))
        self.cooldown_ticks = max(0, int(self.config.get("cooldown_ticks", 60) or 0))
        self.los_required = bool(self.config.get("los_required", False))
        self.repath_min_ticks = max(1, int(self.config.get("repath_min_ticks", 2) or 2))
        self.no_path_repath_ticks = max(1, int(self.config.get("no_path_repath_ticks", 10) or 10))

        self.state: str = "idle"  # idle|chase|cooldown
        self._cooldown_remaining: int = 0
        self._no_path_ticks: int = 0
        self._target = None
        self._follow: FollowPathBehaviour | None = None

    def update(self, dt: float) -> None:
        if dt <= 0:
            return
        if self.speed <= 0:
            return

        grid = self._get_nav_grid()
        if grid is None:
            return

        if self.state == "cooldown":
            self._cooldown_remaining = max(0, self._cooldown_remaining - 1)
            if self._cooldown_remaining <= 0:
                self.state = "idle"
            return

        if self.state == "idle":
            target = self._acquire_target(grid)
            if target is None:
                return
            self._enter_chase(target)

        if self.state != "chase":
            return

        target = self._target
        if target is None:
            self._disengage()
            return

        dist_tiles = self._distance_tiles_to(target, grid)
        if dist_tiles > float(self.leash_radius_tiles):
            self._disengage()
            return
        if self.stop_range_tiles > 0 and dist_tiles <= float(self.stop_range_tiles):
            self._no_path_ticks = 0
            return

        follow = self._follow
        if follow is None:
            self._disengage()
            return

        follow.goal_x = float(getattr(target, "center_x", 0.0))
        follow.goal_y = float(getattr(target, "center_y", 0.0))
        follow.update(dt)

        if follow.state == "no_path":
            self._no_path_ticks += 1
            if self._no_path_ticks > self.give_up_ticks:
                self._enter_cooldown()
        else:
            self._no_path_ticks = 0

    def _get_nav_grid(self) -> NavGrid | None:
        scene = getattr(self.window, "scene_controller", None)
        getter = getattr(scene, "get_nav_grid", None) if scene is not None else None
        if callable(getter):
            return getter()
        return None

    @staticmethod
    def _entity_id(sprite: Any) -> str:
        payload = getattr(sprite, "mesh_entity_data", None)
        if isinstance(payload, dict):
            raw = payload.get("id") or payload.get("entity_id")
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
        raw = getattr(sprite, "mesh_name", None)
        return str(raw).strip() if raw is not None else ""

    def _iter_candidates(self) -> list[Any]:
        scene = getattr(self.window, "scene_controller", None)
        getter = getattr(scene, "get_all_entities", None) if scene is not None else None
        if callable(getter):
            return list(getter())
        all_sprites = getattr(scene, "all_sprites", None) if scene is not None else None
        if all_sprites is None:
            return []
        return list(all_sprites)

    def _resolve_target_by_id(self, entity_id: str) -> Any | None:
        scene = getattr(self.window, "scene_controller", None)
        ensure = getattr(scene, "_ensure_scene_index", None) if scene is not None else None
        if callable(ensure):
            idx = ensure()
            getter = getattr(idx, "get_by_id", None)
            if callable(getter):
                sprite = getter(entity_id)
                if sprite is not None:
                    return sprite
        for sprite in self._iter_candidates():
            if self._entity_id(sprite) == entity_id:
                return sprite
        return None

    def _distance_tiles_to(self, sprite: Any, grid: NavGrid) -> float:
        sx, sy = grid.world_to_tile(float(getattr(self.entity, "center_x", 0.0)), float(getattr(self.entity, "center_y", 0.0)))
        tx, ty = grid.world_to_tile(float(getattr(sprite, "center_x", 0.0)), float(getattr(sprite, "center_y", 0.0)))
        return math.hypot(float(tx - sx), float(ty - sy))

    def _acquire_target(self, grid: NavGrid) -> Any | None:
        target = None
        if self.target_entity_id:
            target = self._resolve_target_by_id(self.target_entity_id)
            if target is None:
                return None
            if self._distance_tiles_to(target, grid) > float(self.acquire_radius_tiles):
                return None
            if self.los_required and not self._has_los_to(target, grid):
                return None
            return target

        if not self.target_tag:
            return None

        best = None
        best_dist: float | None = None
        best_id = ""

        for sprite in self._iter_candidates():
            if sprite is self.entity:
                continue
            tag = getattr(sprite, "mesh_tag", None)
            if str(tag or "").strip() != self.target_tag:
                continue
            dist = self._distance_tiles_to(sprite, grid)
            if dist > float(self.acquire_radius_tiles):
                continue
            if self.los_required and not self._has_los_to(sprite, grid):
                continue
            eid = self._entity_id(sprite)
            if best is None or (best_dist is not None and dist < best_dist) or (best_dist is not None and dist == best_dist and eid < best_id):
                best = sprite
                best_dist = dist
                best_id = eid

        return best

    def _has_los_to(self, sprite: Any, grid: NavGrid) -> bool:
        start = grid.world_to_tile(float(getattr(self.entity, "center_x", 0.0)), float(getattr(self.entity, "center_y", 0.0)))
        goal = grid.world_to_tile(float(getattr(sprite, "center_x", 0.0)), float(getattr(sprite, "center_y", 0.0)))
        return line_of_sight_clear(start, goal, grid)

    def _enter_chase(self, target: Any) -> None:
        self.state = "chase"
        self._target = target
        self._no_path_ticks = 0
        self._follow = FollowPathBehaviour(
            self.entity,
            self.window,
            goal_x=float(getattr(target, "center_x", 0.0)),
            goal_y=float(getattr(target, "center_y", 0.0)),
            speed=float(self.speed),
            repath_interval=0.0,
            repath_min_ticks=int(self.repath_min_ticks),
            no_path_repath_ticks=int(self.no_path_repath_ticks),
            arrive_dist=2.0,
            diag=False,
        )

    def _disengage(self) -> None:
        self.state = "idle"
        self._target = None
        self._follow = None
        self._no_path_ticks = 0

    def _enter_cooldown(self) -> None:
        self.state = "cooldown"
        self._cooldown_remaining = int(self.cooldown_ticks)
        self._target = None
        self._follow = None
        self._no_path_ticks = 0
