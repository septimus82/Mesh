from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Iterable, TypeGuard

from engine.path_norm import normalize_scene_path
from engine.paths import resolve_path


@dataclass(frozen=True)
class SpawnPlaceholderSafetyIssue:
    scene_path: str
    placeholder_id: str
    reason: str
    offending_target_id: str
    distance: float
    sort_key: tuple[Any, ...]


def _non_empty_str(value: object | None) -> str | None:
    text = str(value or "").strip()
    return text or None


def _is_number(value: object) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _iter_behaviour_types(entity: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    behaviours = entity.get("behaviours")
    if isinstance(behaviours, list):
        for item in behaviours:
            if isinstance(item, str) and item.strip():
                out.add(item.strip())
            elif isinstance(item, dict):
                kind = _non_empty_str(item.get("type"))
                if kind:
                    out.add(kind)
    elif isinstance(behaviours, dict):
        for key, value in behaviours.items():
            if isinstance(key, str) and key.strip() and isinstance(value, dict):
                out.add(key.strip())

    behaviour_config = entity.get("behaviour_config")
    if isinstance(behaviour_config, dict):
        for key in behaviour_config.keys():
            if isinstance(key, str) and key.strip():
                out.add(key.strip())
    return out


def _distance(ax: float, ay: float, bx: float, by: float) -> float:
    return float(math.hypot(float(ax) - float(bx), float(ay) - float(by)))


def _sorted_issues(issues: Iterable[SpawnPlaceholderSafetyIssue]) -> list[SpawnPlaceholderSafetyIssue]:
    return sorted(list(issues), key=lambda i: i.sort_key)


def validate_spawn_placeholder_safety(
    scene_paths: list[str],
    *,
    min_dist: float = 48.0,
) -> dict[str, Any]:
    """Validate theme_enemy_placeholder placement safety for the provided scene paths.

    Tooling-only guard: does not change gameplay. Checks placeholders are not too close to player start,
    too close to scene transitions/doors, and not inside TriggerZone radii.
    """
    min_dist_val = float(min_dist)
    raw_scene_paths = [str(p) for p in scene_paths if str(p or "").strip()]
    scene_path_map: dict[str, str] = {}
    for raw in raw_scene_paths:
        display = normalize_scene_path(raw)
        if not display:
            continue
        scene_path_map.setdefault(display, raw)

    issues: list[SpawnPlaceholderSafetyIssue] = []
    for display_path, raw_path in sorted(scene_path_map.items(), key=lambda kv: kv[0]):
        resolved = resolve_path(raw_path)
        if not resolved.exists():
            continue

        try:
            data = json.loads(resolved.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue

        entities = data.get("entities")
        if entities is None:
            entities = []
        if not isinstance(entities, list):
            continue

        player_start: tuple[float, float] | None = None
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            if _non_empty_str(entity.get("tag")) == "player":
                x = entity.get("x")
                y = entity.get("y")
                if _is_number(x) and _is_number(y):
                    player_start = (float(x), float(y))
                    break

        transition_points: list[tuple[str, float, float]] = []
        trigger_zones: list[tuple[str, float, float, float]] = []  # (zone_id, x, y, radius)
        placeholders: list[tuple[str, float, float]] = []

        for entity in entities:
            if not isinstance(entity, dict):
                continue
            x = entity.get("x")
            y = entity.get("y")
            if not (_is_number(x) and _is_number(y)):
                continue
            ex = float(x)
            ey = float(y)

            entity_id = _non_empty_str(entity.get("id")) or _non_empty_str(entity.get("name")) or "<entity>"
            types = _iter_behaviour_types(entity)

            if _non_empty_str(entity.get("prefab_id")) == "theme_enemy_placeholder":
                placeholders.append((entity_id, ex, ey))

            if "SceneTransition" in types:
                transition_points.append((entity_id, ex, ey))

            if "TriggerZone" in types:
                cfg = entity.get("behaviour_config")
                tz = cfg.get("TriggerZone") if isinstance(cfg, dict) else None
                radius = tz.get("trigger_radius") if isinstance(tz, dict) else None
                zone_id = _non_empty_str(tz.get("zone_id")) if isinstance(tz, dict) else None
                zone_key = zone_id or entity_id
                if _is_number(radius) and float(radius) > 0.0:
                    trigger_zones.append((zone_key, ex, ey, float(radius)))

        for placeholder_id, px, py in placeholders:
            if player_start is not None:
                d = _distance(px, py, player_start[0], player_start[1])
                if d < min_dist_val:
                    issues.append(
                        SpawnPlaceholderSafetyIssue(
                            scene_path=display_path,
                            placeholder_id=placeholder_id,
                            reason="near_player_start",
                            offending_target_id="player_start",
                            distance=d,
                            sort_key=(display_path, placeholder_id, "near_player_start", "player_start"),
                        )
                    )

            for target_id, tx, ty in transition_points:
                d = _distance(px, py, tx, ty)
                if d < min_dist_val:
                    issues.append(
                        SpawnPlaceholderSafetyIssue(
                            scene_path=display_path,
                            placeholder_id=placeholder_id,
                            reason="near_transition",
                            offending_target_id=target_id,
                            distance=d,
                            sort_key=(display_path, placeholder_id, "near_transition", str(target_id)),
                        )
                    )

            for zone_id, zx, zy, radius in trigger_zones:
                d = _distance(px, py, zx, zy)
                if d <= float(radius):
                    issues.append(
                        SpawnPlaceholderSafetyIssue(
                            scene_path=display_path,
                            placeholder_id=placeholder_id,
                            reason="inside_trigger_zone",
                            offending_target_id=zone_id,
                            distance=d,
                            sort_key=(display_path, placeholder_id, "inside_trigger_zone", str(zone_id)),
                        )
                    )

    issues_sorted = _sorted_issues(issues)
    return {
        "ok": len(issues_sorted) == 0,
        "scene_count": len(scene_path_map),
        "min_dist": min_dist_val,
        "issues": [
            {
                "scene_path": i.scene_path,
                "placeholder_id": i.placeholder_id,
                "reason": i.reason,
                "offending_target_id": i.offending_target_id,
                "distance": i.distance,
            }
            for i in issues_sorted
        ],
    }
