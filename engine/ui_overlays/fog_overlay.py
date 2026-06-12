from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

import engine.optional_arcade as optional_arcade

from .common import UIElement, _draw_rectangle_filled

if TYPE_CHECKING:  # pragma: no cover
    from ..game import GameWindow


def _normalize_rgba(value: Any) -> tuple[int, int, int, int]:
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        try:
            r = int(value[0])
            g = int(value[1])
            b = int(value[2])
            a = int(value[3]) if len(value) > 3 else 255
            return (r, g, b, a)
        except Exception:  # noqa: BLE001  # REASON: fog overlay should fall back to a transparent color when config values are malformed
            return (255, 255, 255, 0)
    return (255, 255, 255, 0)


def resolve_fog_rgba(
    engine_cfg: Any,
    scene_settings: Any,
    ambient_rgba: Any | None,
) -> tuple[int, int, int, int]:
    if isinstance(scene_settings, dict) and "fog_rgba" in scene_settings:
        return _normalize_rgba(scene_settings.get("fog_rgba"))
    cfg_rgba = getattr(engine_cfg, "fog_rgba", (255, 255, 255, 0))
    if _normalize_rgba(cfg_rgba) != (255, 255, 255, 0):
        return _normalize_rgba(cfg_rgba)
    if ambient_rgba is None:
        ambient_rgba = getattr(engine_cfg, "ambient_light_rgba", (255, 255, 255, 255))
    ambient = _normalize_rgba(ambient_rgba)
    return (ambient[0], ambient[1], ambient[2], 255)


def _fog_noise_value(time_s: float, speed: float, seed: int) -> float:
    if speed <= 0.0:
        return 0.0
    phase = float(seed) * 0.12345
    return math.sin(time_s * speed * math.tau + phase)


def compute_fog_rgba(
    *,
    enabled: bool,
    fog_rgba: Any,
    density: float,
    noise_amount: float,
    noise_speed: float,
    time_s: float,
    seed: int = 0,
) -> tuple[int, int, int, int] | None:
    if not enabled:
        return None
    rgba = _normalize_rgba(fog_rgba)
    density = max(0.0, min(1.0, float(density)))
    base_alpha = float(rgba[3]) * density
    if base_alpha <= 0.0:
        return None
    noise_amount = max(0.0, min(1.0, float(noise_amount)))
    noise_speed = max(0.0, float(noise_speed))
    noise = _fog_noise_value(float(time_s), noise_speed, int(seed))
    alpha = base_alpha * (1.0 + noise_amount * noise)
    alpha = max(0.0, min(255.0, alpha))
    return (rgba[0], rgba[1], rgba[2], int(round(alpha)))


class FogOverlay(UIElement):
    """World-space fog overlay drawn after lighting composite."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self._time_s = 0.0
        self._seed = 0

    def update(self, dt: float) -> None:
        self._time_s += float(dt)

    def draw(self) -> None:
        return

    def _resolve_fog_settings(self) -> dict[str, Any]:
        cfg = getattr(self.window, "engine_config", None)
        settings = getattr(getattr(self.window, "scene_controller", None), "scene_settings", None)
        ambient_rgba = getattr(cfg, "ambient_light_rgba", (255, 255, 255, 255))
        if isinstance(settings, dict) and "ambient_light_rgba" in settings:
            ambient_rgba = settings.get("ambient_light_rgba")
        fog_rgba = resolve_fog_rgba(cfg, settings, ambient_rgba)
        resolved: dict[str, Any] = {
            "enabled": bool(getattr(cfg, "fog_enabled", False)),
            "fog_rgba": fog_rgba,
            "density": getattr(cfg, "fog_density", 0.0),
            "noise_speed": getattr(cfg, "fog_noise_speed", 0.15),
            "noise_amount": getattr(cfg, "fog_noise_amount", 0.25),
        }
        if isinstance(settings, dict):
            if "fog_enabled" in settings:
                resolved["enabled"] = bool(settings.get("fog_enabled"))
            if "fog_density" in settings:
                resolved["density"] = settings.get("fog_density")
            if "fog_noise_speed" in settings:
                resolved["noise_speed"] = settings.get("fog_noise_speed")
            if "fog_noise_amount" in settings:
                resolved["noise_amount"] = settings.get("fog_noise_amount")
        runtime_settings = getattr(self.window, "runtime_settings", None)
        if runtime_settings is not None and hasattr(runtime_settings, "fog_enabled"):
            resolved["enabled"] = bool(getattr(runtime_settings, "fog_enabled", resolved["enabled"]))
        return resolved

    def _camera_view_rect(self) -> tuple[float, float, float, float]:
        center_x, center_y = self.window.get_camera_center()
        zoom = 1.0
        controller = getattr(self.window, "camera_controller", None)
        if controller is not None:
            zoom_state = getattr(controller, "zoom_state", None)
            if zoom_state is not None:
                zoom = float(getattr(zoom_state, "current", 1.0) or 1.0)
        width = float(getattr(self.window, "width", 0) or 0) / max(1e-6, zoom)
        height = float(getattr(self.window, "height", 0) or 0) / max(1e-6, zoom)
        return (float(center_x), float(center_y), width, height)

    def draw_world(self) -> None:
        if optional_arcade.arcade is None:
            return
        resolved = self._resolve_fog_settings()
        rgba = compute_fog_rgba(
            enabled=bool(resolved.get("enabled", False)),
            fog_rgba=resolved.get("fog_rgba"),
            density=float(resolved.get("density", 0.0) or 0.0),
            noise_amount=float(resolved.get("noise_amount", 0.0) or 0.0),
            noise_speed=float(resolved.get("noise_speed", 0.0) or 0.0),
            time_s=self._time_s,
            seed=self._seed,
        )
        if rgba is None:
            return
        cx, cy, width, height = self._camera_view_rect()
        _draw_rectangle_filled(cx, cy, width, height, rgba)
