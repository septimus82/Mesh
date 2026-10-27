"""A room's wind (Milestone 20E): one signal that rain, snow, windborne leaves and swaying plants all read, so they
agree on which way and how hard it blows.

    "settings": {"wind": {"speed": 4.0, "direction": 20, "gust": 0.5}}

- ``speed``: m/s (0-30), the wind's mean speed. 0 (or no ``wind``): calm.
- ``direction``: degrees the wind blows *toward*, counter-clockwise from east (0 east, 90 north), as a particle
  effect's ``wind`` vector [east, north] points.
- ``gust``: 0-1, how much it swells and drops: at a place and time the wind is ``speed * (1 + gust * g)``, ``g``
  between -1 and 1. Gusts are fronts travelling with the wind (``gust_wave``), so neighbouring plants feel one a
  moment apart and the meadow ripples in waves rather than all at once.

A particle effect without its own ``wind`` or ``gust`` takes the room's (engine.scene_particles); one with its own
keeps it, so rooms made before the room's wind behave as they did. The gusts' rate matches the particles'
(about 0.7 radians a second, a swell every nine seconds), so a gust in the rain and one in the grass mean the same
thing; a raindrop's gust is its own (drops are not tied to a place), a plant's is the front passing over it.

Everything is a function of the time and place alone (never of the frame), so it looks the same at any frame rate.
Time runs modulo ``PERIOD`` on the GPU (its 32-bit floats would grow coarse over hours); every rate here is a whole
number of turns a period, so the wrap is seamless.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

PERIOD = 3600.0  # s: the motion clock wraps here (seamlessly: every rate below turns a whole number of times)
W1 = 2 * math.pi * 401 / PERIOD  # rad/s: the main swell (0.6999: the particles' 0.7)
W2 = 2 * math.pi * 649 / PERIOD  # rad/s: a second, out of step, so the swells never repeat exactly
ACROSS = 0.35  # rad/m: gust fronts are patches, not endless straight lines
MAX_SPEED = 30.0


class WindError(ValueError):
    """A room's wind settings can't be used."""


@dataclass(frozen=True)
class Wind:
    speed: float = 0.0  # m/s
    direction: float = 0.0  # degrees toward, counter-clockwise from east
    gust: float = 0.0  # 0..1

    @property
    def vector(self) -> tuple[float, float]:
        """m/s (east, north)."""
        a = math.radians(self.direction)
        return (self.speed * math.cos(a), self.speed * math.sin(a))

    @property
    def calm(self) -> bool:
        return self.speed <= 0.0


CALM = Wind()


def parse_wind(raw: Any, where: str = "settings.wind") -> Wind:
    """A room's ``settings.wind`` checked; None: calm."""
    if raw is None:
        return CALM
    if not isinstance(raw, dict):
        raise WindError(f'{where} must be an object like {{"speed": 4, "direction": 0, "gust": 0.5}}')
    unknown = set(raw) - {"speed", "direction", "gust"}
    if unknown:
        raise WindError(f"{where}: unknown setting(s) {', '.join(sorted(unknown))}")
    out = []
    for key, lo, hi in (("speed", 0.0, MAX_SPEED), ("direction", -360.0, 360.0), ("gust", 0.0, 1.0)):
        value = raw.get(key, 0.0)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) \
                or not lo <= value <= hi:
            raise WindError(f"{where}.{key} must be a number from {lo:g} to {hi:g} (got {value!r})")
        out.append(float(value))
    return Wind(out[0], out[1] % 360.0, out[2])


def stored(wind: Wind) -> dict[str, float] | None:
    """As saved (None: calm, nothing written)."""
    if wind.calm:
        return None
    return {"speed": round(wind.speed, 3), "direction": round(wind.direction, 3), "gust": round(wind.gust, 3)}


def gust_wave(x: float, y: float, t: float, wind: Wind) -> float:
    """``g`` (-1..1) at (x, y) m, time t s: fronts moving with the wind. The GLSL ``gust_wave`` is this, line for line."""
    vx, vy = wind.vector
    s = math.hypot(vx, vy)
    dx, dy = (vx / s, vy / s) if s > 0 else (1.0, 0.0)
    along, across = x * dx + y * dy, -x * dy + y * dx
    a = t - along / max(1.5, s)
    return 0.65 * math.sin(W1 * a + ACROSS * across) + 0.35 * math.sin(W2 * a + 1.3 - 0.6 * ACROSS * across)


def speed_at(x: float, y: float, t: float, wind: Wind) -> float:
    """m/s at (x, y) m and time t s: the mean speed, swelling and dropping with the gusts (never below 0)."""
    return wind.speed * max(0.0, 1.0 + wind.gust * gust_wave(x, y, t, wind))


GLSL = """
const float W1 = %r, W2 = %r, ACROSS = %r;
float gust_wave(vec2 p, float t, vec2 wind) {
    float s = length(wind);
    vec2 d = s > 0.0 ? wind / s : vec2(1.0, 0.0);
    float along = dot(p, d), across = -p.x * d.y + p.y * d.x;
    float a = t - along / max(1.5, s);
    return 0.65 * sin(W1 * a + ACROSS * across) + 0.35 * sin(W2 * a + 1.3 - 0.6 * ACROSS * across);
}
""" % (W1, W2, ACROSS)
