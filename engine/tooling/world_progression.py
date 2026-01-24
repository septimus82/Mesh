from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine.paths import resolve_path
from engine.path_norm import normalize_scene_path


@dataclass(frozen=True)
class WorldProgressionResult:
    ok: bool
    world_path: str
    start_scene_key: str | None
    start_scene_path: str | None
    required_scene_paths: tuple[str, ...]
    missing_scene_paths: tuple[str, ...]


def _scene_key_for_path(world_data: dict[str, Any], scene_path: str) -> str | None:
    scenes = world_data.get("scenes")
    if not isinstance(scenes, dict):
        return None
    target = normalize_scene_path(scene_path)
    if not target:
        return None
    for key, raw in scenes.items():
        if not isinstance(raw, dict):
            continue
        candidate = raw.get("path")
        if not isinstance(candidate, str):
            continue
        if normalize_scene_path(candidate) == target:
            return str(key)
    return None


def _build_adjacency(world_data: dict[str, Any]) -> dict[str, list[str]]:
    scenes = world_data.get("scenes")
    if not isinstance(scenes, dict):
        return {}
    links = world_data.get("links")
    if not isinstance(links, list):
        links = []

    adj: dict[str, list[str]] = {str(k): [] for k in scenes.keys()}
    for raw in links:
        if not isinstance(raw, dict):
            continue
        src = raw.get("from")
        dst = raw.get("to")
        if src in adj and dst in scenes:
            adj[str(src)].append(str(dst))
    return adj


def check_world_progression(
    world_path: str,
    *,
    required_scene_paths: list[str] | tuple[str, ...],
) -> WorldProgressionResult:
    resolved = resolve_path(world_path)
    if not resolved.exists():
        return WorldProgressionResult(
            ok=True,
            world_path=normalize_scene_path(world_path),
            start_scene_key=None,
            start_scene_path=None,
            required_scene_paths=tuple(normalize_scene_path(p) for p in required_scene_paths),
            missing_scene_paths=tuple(),
        )

    world_data = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(world_data, dict):
        return WorldProgressionResult(
            ok=False,
            world_path=normalize_scene_path(world_path),
            start_scene_key=None,
            start_scene_path=None,
            required_scene_paths=tuple(normalize_scene_path(p) for p in required_scene_paths),
            missing_scene_paths=tuple(sorted(normalize_scene_path(p) for p in required_scene_paths)),
        )

    scenes = world_data.get("scenes")
    if not isinstance(scenes, dict) or not scenes:
        return WorldProgressionResult(
            ok=False,
            world_path=normalize_scene_path(world_path),
            start_scene_key=None,
            start_scene_path=None,
            required_scene_paths=tuple(normalize_scene_path(p) for p in required_scene_paths),
            missing_scene_paths=tuple(sorted(normalize_scene_path(p) for p in required_scene_paths)),
        )

    start_key = world_data.get("start_scene")
    if not isinstance(start_key, str) or not start_key.strip():
        start_key = next(iter(scenes.keys()))
    start_key = str(start_key)

    start_scene_path = None
    start_def = scenes.get(start_key)
    if isinstance(start_def, dict) and isinstance(start_def.get("path"), str):
        start_scene_path = normalize_scene_path(start_def["path"])

    adj = _build_adjacency(world_data)
    if start_key not in adj:
        return WorldProgressionResult(
            ok=False,
            world_path=normalize_scene_path(world_path),
            start_scene_key=start_key,
            start_scene_path=start_scene_path,
            required_scene_paths=tuple(normalize_scene_path(p) for p in required_scene_paths),
            missing_scene_paths=tuple(sorted(normalize_scene_path(p) for p in required_scene_paths)),
        )

    visited: set[str] = {start_key}
    queue: deque[str] = deque([start_key])
    while queue:
        curr = queue.popleft()
        for neighbor in adj.get(curr, []):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)

    missing: list[str] = []
    for required in required_scene_paths:
        normalized = normalize_scene_path(str(required))
        key = _scene_key_for_path(world_data, normalized)
        if key is None or key not in visited:
            missing.append(normalized)

    missing_sorted = tuple(sorted(set(missing)))
    return WorldProgressionResult(
        ok=len(missing_sorted) == 0,
        world_path=normalize_scene_path(world_path),
        start_scene_key=start_key,
        start_scene_path=start_scene_path,
        required_scene_paths=tuple(normalize_scene_path(p) for p in required_scene_paths),
        missing_scene_paths=missing_sorted,
    )


def world_progression_result_to_payload(result: WorldProgressionResult) -> dict[str, Any]:
    return {
        "ok": bool(result.ok),
        "world_path": str(result.world_path),
        "start_scene_key": result.start_scene_key,
        "start_scene_path": result.start_scene_path,
        "required_scene_paths": list(result.required_scene_paths),
        "missing_scene_paths": list(result.missing_scene_paths),
    }
