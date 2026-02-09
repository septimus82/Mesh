from __future__ import annotations

from typing import Any, Callable

from engine.pathfinding import NavGrid, NavGridCache, build_nav_grid_from_tilemap_instance
from engine.scene_navigation_model import NavInputs, build_nav_cache_plan


class SceneNavigationController:
    def __init__(self) -> None:
        self._nav_grid_cache: NavGridCache[NavGrid] = NavGridCache()

    def invalidate(self) -> None:
        self._nav_grid_cache.invalidate()

    def get_nav_grid(
        self,
        *,
        scene_path: str | None,
        revision: int,
        tilemap_instance: Any,
        build_fn: Callable[[Any], NavGrid | None] | None = None,
    ) -> NavGrid | None:
        plan = build_nav_cache_plan(NavInputs(scene_path=scene_path, revision=revision))
        builder = build_fn or build_nav_grid_from_tilemap_instance

        def _build() -> NavGrid | None:
            return builder(tilemap_instance)

        return self._nav_grid_cache.get_or_build(
            scene_path=plan.scene_path,
            revision=plan.revision,
            build=_build,
        )
