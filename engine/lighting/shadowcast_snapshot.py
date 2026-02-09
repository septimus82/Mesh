"""Shadowcast snapshot helpers for lighting debug."""

from __future__ import annotations

import math
from typing import Any

from . import polygon_raycaster as _polygon_raycaster


def build_shadowcast_snapshot(manager: Any) -> dict[str, Any]:
    shadowcast: dict[str, Any] = {}
    angles = [i * (2 * math.pi / 16) for i in range(16)]

    for i, light in enumerate(manager._static_configs):
        light_id = f"light_{i}"
        lx = light.get("x", 0.0)
        ly = light.get("y", 0.0)
        radius = light.get("radius", 100.0)

        rays = []
        for angle in angles:
            rays.append(_polygon_raycaster.cast_ray(manager, (lx, ly), angle, radius))

        shadowcast[light_id] = rays

    return shadowcast
