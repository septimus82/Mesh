from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(slots=True)
class FlickerNoise:
    seed: int

    def __init__(self, seed: int) -> None:
        self.seed = int(seed)

    def _hash(self, value: int) -> int:
        x = (value + self.seed * 374761393) & 0xFFFFFFFF
        x ^= (x >> 13)
        x = (x * 1274126177) & 0xFFFFFFFF
        x ^= (x >> 16)
        return x & 0xFFFFFFFF

    def _value(self, value: int) -> float:
        hashed = self._hash(int(value))
        return (hashed / 0xFFFFFFFF) * 2.0 - 1.0

    def sample(self, t: float) -> float:
        t = float(t)
        i0 = math.floor(t)
        i1 = i0 + 1
        frac = t - i0
        smooth = frac * frac * (3.0 - 2.0 * frac)
        v0 = self._value(i0)
        v1 = self._value(i1)
        return max(-1.0, min(1.0, v0 + (v1 - v0) * smooth))


def apply_light_flicker(
    *,
    base_radius: float,
    base_color: tuple[int, int, int, int],
    noise: FlickerNoise,
    time_s: float,
    speed: float,
    amount: float,
    radius_px: float | None,
    intensity: float | None,
) -> tuple[float, tuple[int, int, int, int]]:
    base_radius = float(base_radius)
    speed = max(0.0, float(speed))
    amount = max(0.0, min(float(amount), 1.0))
    if radius_px is not None:
        radius_px = float(radius_px)
    if intensity is not None:
        intensity = max(0.0, min(float(intensity), 1.0))

    sample = noise.sample(float(time_s) * speed)
    if radius_px is not None:
        radius = base_radius + radius_px * sample
    else:
        radius = base_radius * (1.0 + amount * sample)
    radius = max(0.0, radius)

    intensity_amount = amount if intensity is None else intensity
    scale = max(0.0, 1.0 + intensity_amount * sample)
    r, g, b, a = base_color
    color = (
        int(round(max(0.0, min(255.0, r * scale)))),
        int(round(max(0.0, min(255.0, g * scale)))),
        int(round(max(0.0, min(255.0, b * scale)))),
        int(round(max(0.0, min(255.0, a * scale)))),
    )
    return radius, color
