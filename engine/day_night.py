"""Simple day/night cycle that drives LightManager ambient color."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from .lighting import LightManager

Color = Tuple[int, int, int, int]


@dataclass
class TimeKey:
    hour: float
    color: Color


def _lerp_color(a: Color, b: Color, t: float) -> Color:
    inv = 1.0 - t
    return (
        int(a[0] * inv + b[0] * t),
        int(a[1] * inv + b[1] * t),
        int(a[2] * inv + b[2] * t),
        int(a[3] * inv + b[3] * t),
    )


class DayNightCycle:
    """Global time-of-day system driving LightManager.ambient_color."""

    def __init__(
        self,
        lighting: LightManager,
        *,
        enabled: bool = True,
        start_hour: float = 21.0,
        cycle_length_seconds: float = 600.0,
        keys: List[TimeKey] | None = None,
    ) -> None:
        self.lighting = lighting
        self.enabled = bool(enabled)
        self._hour = float(start_hour) % 24.0
        self.set_cycle_length_seconds(cycle_length_seconds)
        if keys is None:
            self._keys = self._default_keys()
        else:
            self._keys = sorted(keys, key=lambda k: k.hour)
        self._apply_ambient()

    def _default_keys(self) -> List[TimeKey]:
        return [
            TimeKey(0.0, (5, 5, 15, 255)),
            TimeKey(5.5, (80, 60, 100, 255)),
            TimeKey(12.0, (185, 185, 210, 255)),
            TimeKey(18.5, (120, 80, 80, 255)),
            TimeKey(23.0, (10, 10, 20, 255)),
        ]

    @property
    def hour(self) -> float:
        """Current time-of-day as hour [0,24)."""
        return self._hour

    def set_hour(self, hour: float) -> None:
        self._hour = float(hour) % 24.0
        self._apply_ambient()

    def set_cycle_length_seconds(self, seconds: float) -> None:
        seconds = max(1.0, float(seconds))
        self._cycle_length_seconds = seconds
        self._hours_per_second = 24.0 / seconds

    def set_enabled(self, value: bool) -> None:
        self.enabled = bool(value)
        if self.enabled:
            self._apply_ambient()

    def update(self, delta_time: float) -> None:
        if not self.enabled:
            return
        self._hour = (self._hour + self._hours_per_second * delta_time) % 24.0
        self._apply_ambient()

    def compute_ambient_rgb(self) -> tuple[int, int, int]:
        """Return ambient RGB without alpha for the current time."""
        color = self._interpolated_color(self._hour)
        return (color[0], color[1], color[2])

    def _apply_ambient(self) -> None:
        color = self._interpolated_color(self._hour)
        try:
            self.lighting.ambient_color = color
        except Exception as exc:  # noqa: BLE001
            if not getattr(self, "_mesh_ambient_error_logged", False):
                print(f"[Mesh][DayNight] WARNING: Failed to set ambient_color: {exc!r}")
                setattr(self, "_mesh_ambient_error_logged", True)

    def _interpolated_color(self, hour: float) -> Color:
        keys = self._keys
        if not keys:
            return (10, 10, 10, 255)
        keys = sorted(keys, key=lambda k: k.hour)
        prev = keys[-1]
        next_key = keys[0]
        for k in keys:
            if k.hour >= hour:
                next_key = k
                break
            prev = k
        h0, c0 = prev.hour, prev.color
        h1, c1 = next_key.hour, next_key.color
        if h1 <= h0:
            h1 += 24.0
        if hour < h0:
            hour += 24.0
        t = 0.0 if h1 == h0 else (hour - h0) / (h1 - h0)
        t = max(0.0, min(1.0, t))
        return _lerp_color(c0, c1, t)
