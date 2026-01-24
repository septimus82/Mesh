from __future__ import annotations

import math
from typing import Any


def _normalize_color(value: Any) -> tuple[int, int, int, int]:
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        try:
            r = int(value[0])
            g = int(value[1])
            b = int(value[2])
            a = int(value[3]) if len(value) >= 4 else 255
            return (
                max(0, min(255, r)),
                max(0, min(255, g)),
                max(0, min(255, b)),
                max(0, min(255, a)),
            )
        except Exception:  # noqa: BLE001
            return (255, 255, 255, 255)
    return (255, 255, 255, 255)


def compute_shafts_alpha(base_alpha: float, t: float, speed: float, amount: float) -> float:
    base = max(0.0, min(1.0, float(base_alpha)))
    if base <= 0.0:
        return 0.0
    speed = max(0.0, float(speed))
    amount = max(0.0, min(1.0, float(amount)))
    if speed <= 0.0 or amount <= 0.0:
        return base
    wave = math.sin(float(t) * speed * math.tau)
    return max(0.0, min(1.0, base * (1.0 + amount * wave)))


def build_shafts_params(
    light_world_pos: tuple[float, float],
    color_rgba: Any,
    radius: float,
    cfg: dict[str, Any] | None,
    t: float,
) -> dict[str, Any] | None:
    if not isinstance(cfg, dict):
        return None
    if not bool(cfg.get("shafts_enabled", False)):
        return None
    length_px = float(cfg.get("shafts_length_px", 220.0))
    width_px = float(cfg.get("shafts_width_px", 140.0))
    if length_px <= 0.0 or width_px <= 0.0:
        return None
    rotation_deg = float(cfg.get("shafts_rotation_deg", 0.0))
    base_alpha = float(cfg.get("shafts_alpha", 0.35))
    noise_speed = float(cfg.get("shafts_noise_speed", 0.08))
    noise_amount = float(cfg.get("shafts_noise_amount", 0.15))
    alpha = compute_shafts_alpha(base_alpha, float(t), noise_speed, noise_amount)
    if alpha <= 0.0:
        return None
    color = _normalize_color(color_rgba)
    final_alpha = int(round(color[3] * alpha))
    final_alpha = max(0, min(255, final_alpha))
    return {
        "center_x": float(light_world_pos[0]),
        "center_y": float(light_world_pos[1]),
        "length_px": float(length_px),
        "width_px": float(width_px),
        "rotation_deg": float(rotation_deg),
        "alpha": float(alpha),
        "color_rgba": (color[0], color[1], color[2], final_alpha),
        "radius": float(radius),
    }
