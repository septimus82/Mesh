# mypy: ignore-errors
from __future__ import annotations

import math
from typing import Any, Dict

import engine.optional_arcade as optional_arcade
from engine.constants import EVENT_ANIMATION_EVENT


def _handle_animation_event(self, sprite: optional_arcade.arcade.Sprite, payload: Dict[str, Any]) -> None:
    data = dict(payload or {})
    data.setdefault("entity", getattr(sprite, "mesh_name", "<unnamed>"))
    data.setdefault("state", data.get("state"))
    data.setdefault("event", data.get("event"))
    data.setdefault("frame", data.get("frame"))
    data.setdefault("loop", data.get("loop", 0))
    data.setdefault("tag", getattr(sprite, "mesh_tag", None))
    motion = self._apply_animation_root_motion(sprite, data)
    data["position"] = (float(sprite.center_x), float(sprite.center_y))
    if motion is not None:
        dx, dy = motion
        data.setdefault("root_motion", {"dx": dx, "dy": dy})
    self.window.emit_signal(EVENT_ANIMATION_EVENT, **data)
    if self.window.show_debug:
        print(
            "[Mesh][Animation] EVENT",
            f"{data['entity']}::{data.get('state', '<unknown>')} -> {data.get('event', '<none>')}",
            f"(frame {data.get('frame')}, loop {data.get('loop')})",
        )


def _apply_animation_root_motion(
    self,
    sprite: optional_arcade.arcade.Sprite,
    event_data: Dict[str, Any],
) -> tuple[float, float] | None:
    config = self._resolve_root_motion_config(sprite)
    if config is None:
        return None
    labels = config.get("labels")
    if labels and event_data.get("event") not in labels:
        return None

    dx, dy = self._extract_root_motion_vector(event_data)
    if dx == 0.0 and dy == 0.0:
        return None

    scale = config.get("scale", 1.0) * self._coerce_float(event_data.get("move_scale", 1.0), 1.0)
    dx *= scale
    dy *= scale

    space = str(event_data.get("space") or config.get("space", "local")).lower()
    if space not in {"local", "world"}:
        space = config.get("space", "local")

    if space == "local":
        angle = math.radians(float(getattr(sprite, "angle", 0.0)))
        world_dx = dx * math.cos(angle) - dy * math.sin(angle)
        world_dy = dx * math.sin(angle) + dy * math.cos(angle)
        dx, dy = world_dx, world_dy

    use_collision = bool(event_data.get("move_collision", config.get("collision", True)))
    if use_collision:
        self.move_entity_with_collision(sprite, dx, dy, 1.0)
    else:
        sprite.center_x += dx
        sprite.center_y += dy

    entity_data = self._ensure_entity_data_dict(sprite)
    entity_data["x"] = float(sprite.center_x)
    entity_data["y"] = float(sprite.center_y)
    return (dx, dy)


def _resolve_root_motion_config(self, sprite: optional_arcade.arcade.Sprite) -> dict[str, Any] | None:
    cache = getattr(sprite, "_mesh_root_motion_config", None)
    if isinstance(cache, dict):
        return cache

    entity_data = getattr(sprite, "mesh_entity_data", None)
    if not isinstance(entity_data, dict):
        return None

    raw = entity_data.get("animation_root_motion")
    config = self._normalize_root_motion_config(raw)
    if config is not None:
        setattr(sprite, "_mesh_root_motion_config", config)
    return config


def _normalize_root_motion_config(self, raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    enabled = True
    settings: dict[str, Any]
    if isinstance(raw, bool):
        enabled = raw
        settings = {}
    elif isinstance(raw, (int, float)):
        enabled = raw != 0
        settings = {"scale": float(raw)}
    elif isinstance(raw, dict):
        settings = dict(raw)
        enabled = bool(settings.pop("enabled", True))
    else:
        return None

    if not enabled:
        return None

    labels = settings.get("labels")
    label_set: set[str] | None = None
    if isinstance(labels, str):
        cleaned = labels.strip()
        label_set = {cleaned} if cleaned else None
    elif isinstance(labels, (list, tuple, set)):
        cleaned = {str(value).strip() for value in labels if isinstance(value, (str, int, float))}
        label_set = {entry for entry in cleaned if entry}
        if not label_set:
            label_set = None

    return {
        "scale": float(settings.get("scale", 1.0)),
        "space": str(settings.get("space", "local")).lower(),
        "collision": bool(settings.get("collision", True)),
        "labels": label_set,
    }


def _extract_root_motion_vector(self, event_data: Dict[str, Any]) -> tuple[float, float]:
    move = event_data.get("move")
    dx, dy = self._coerce_motion_vector(move)
    if dx == 0.0 and dy == 0.0:
        displacement = event_data.get("displacement") or event_data.get("translate")
        dx, dy = self._coerce_motion_vector(displacement)
    if dx == 0.0 and dy == 0.0:
        dx = self._coerce_float(event_data.get("dx"), 0.0)
        dy = self._coerce_float(event_data.get("dy"), 0.0)
    return (dx, dy)


def _coerce_float(self, value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_motion_vector(self, value: Any) -> tuple[float, float]:
    if isinstance(value, (tuple, list)) and len(value) >= 2:
        return (self._coerce_float(value[0]), self._coerce_float(value[1]))
    if isinstance(value, dict):
        return (
            self._coerce_float(value.get("x", 0.0)),
            self._coerce_float(value.get("y", 0.0)),
        )
    return (0.0, 0.0)


def bind_animation_event_sink_methods(cls) -> None:
    cls._handle_animation_event = _handle_animation_event
    cls._apply_animation_root_motion = _apply_animation_root_motion
    cls._resolve_root_motion_config = _resolve_root_motion_config
    cls._normalize_root_motion_config = _normalize_root_motion_config
    cls._extract_root_motion_vector = _extract_root_motion_vector
    cls._coerce_float = _coerce_float
    cls._coerce_motion_vector = _coerce_motion_vector
