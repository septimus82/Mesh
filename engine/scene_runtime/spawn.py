from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from ..scene_index import SceneIndex
from .constants import SPAWN_ID_FIELD, SPAWN_POINT_TAG


def find_spawn_marker(all_sprites: Iterable[Any], spawn_id: str) -> Any | None:
    target = str(spawn_id or "").strip().lower()
    if not target:
        return None
    for sprite in all_sprites:
        tag = getattr(sprite, "mesh_tag", None)
        if str(tag or "").strip().lower() != SPAWN_POINT_TAG:
            continue
        entity_data = getattr(sprite, "mesh_entity_data", {}) or {}
        marker_id = None
        if isinstance(entity_data, dict):
            marker_id = entity_data.get(SPAWN_ID_FIELD) or getattr(sprite, "mesh_name", None)
        else:
            marker_id = getattr(sprite, "mesh_name", None)
        if marker_id is None:
            continue
        if str(marker_id).strip().lower() == target:
            return sprite
    return None


def get_spawn(scene_data: Any, spawn_id: str | None) -> dict[str, Any] | None:
    spawns: dict[str, Any] = {}
    if isinstance(scene_data, dict):
        raw_spawns = scene_data.get("spawns")
        if isinstance(raw_spawns, dict):
            spawns = raw_spawns
    if not spawns:
        return None
    if spawn_id:
        candidate = spawns.get(spawn_id)
        if isinstance(candidate, dict):
            return candidate
    default_spawn = spawns.get("default")
    return default_spawn if isinstance(default_spawn, dict) else None


@dataclass(frozen=True)
class SpawnResolution:
    marker: Any | None
    spawn: dict[str, Any] | None
    resolved: str


def resolve_spawn_target(
    spawn_id: str,
    *,
    all_sprites: Iterable[Any],
    scene_index: SceneIndex,
    scene_data: Any,
) -> SpawnResolution:
    """Resolve a requested spawn target in strict priority order.

    Order:
      marker -> id -> zone_id -> mesh_name -> spawns dict fallback
    """
    marker = find_spawn_marker(all_sprites, spawn_id)
    if marker is not None:
        return SpawnResolution(marker=marker, spawn=None, resolved="marker")

    marker = scene_index.get_by_id(spawn_id)
    if marker is not None:
        return SpawnResolution(marker=marker, spawn=None, resolved="id")

    marker = scene_index.get_by_zone_id(spawn_id)
    if marker is not None:
        return SpawnResolution(marker=marker, spawn=None, resolved="zone_id")

    marker = scene_index.get_first_by_mesh_name(spawn_id)
    if marker is not None:
        return SpawnResolution(marker=marker, spawn=None, resolved="mesh_name")

    spawn = get_spawn(scene_data, spawn_id)
    if spawn is not None:
        return SpawnResolution(marker=None, spawn=spawn, resolved="spawns")

    return SpawnResolution(marker=None, spawn=None, resolved="none")


def apply_pending_spawn_point(controller: Any) -> None:
    spawn_id = controller.window.get_next_spawn_point()
    if not spawn_id:
        return

    marker = find_spawn_marker(controller.all_sprites, spawn_id)
    if marker is None:
        # Prefer deterministic indexed lookups before legacy full scans.
        idx = controller._ensure_scene_index()
        resolution = resolve_spawn_target(
            spawn_id,
            all_sprites=(),
            scene_index=idx,
            scene_data=controller._loaded_scene_data,
        )
        marker = resolution.marker
        spawn = resolution.spawn
    else:
        spawn = None

    if marker is None and spawn is None:
        controller.window.console_log(f"Spawn point '{spawn_id}' not found in this scene")
        return

    player = controller._find_player_sprite()
    if player is None:
        controller.window.console_log("Spawn point requested but no player sprite is available")
        return

    controller.window._consume_next_spawn_point()
    if marker is not None:
        controller._apply_entity_mutation(player, x=marker.center_x, y=marker.center_y)
    else:
        controller.apply_spawn(spawn_id)
    controller.window.console_log(f"Moved player to spawn '{spawn_id}'")
