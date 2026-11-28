from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .types import _FlickerLightState


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


# ------------------------------------------------------------------------------ natural flicker (12.1)
# The old flicker eased between one random value per beat, every 1/speed seconds, and moved only the
# light's reach: a regular "breathing" in and out. A flame flickers in brightness, irregularly, with the
# occasional flare; its lit area barely changes. A faulty lamp is steady until it stutters.


@dataclass(frozen=True, slots=True)
class FlickerProfile:
    """How a light flickers, in creator terms.

    speed: how quickly it changes (about how many wavers a second); brightness: how much it brightens and
    dims (0-1, a fraction of its light); reach: how much its lit area grows and shrinks (0-0.5, a fraction
    of its size); irregularity: 0 a smooth waver, 1 restless and chaotic; flares: occasional brighter
    moments (0-1); dips: a faulty lamp's occasional stutters and drop-outs (0-1).
    """

    speed: float
    brightness: float
    reach: float
    irregularity: float
    flares: float = 0.0
    dips: float = 0.0


FLICKER_PRESETS: dict[str, FlickerProfile] = {
    "candle": FlickerProfile(speed=1.6, brightness=0.10, reach=0.015, irregularity=0.35, flares=0.10),
    "torch": FlickerProfile(speed=2.4, brightness=0.20, reach=0.04, irregularity=0.60, flares=0.30),
    "fire": FlickerProfile(speed=3.4, brightness=0.30, reach=0.08, irregularity=0.85, flares=0.50),
    "faulty": FlickerProfile(speed=1.0, brightness=0.03, reach=0.0, irregularity=0.30, dips=1.0),
}
FLICKER_NAMES = ("steady", "candle", "torch", "fire", "faulty", "custom")
FLICKER_LABELS = {"steady": "Steady", "candle": "Candle", "torch": "Torch", "fire": "Fire", "faulty": "Faulty lamp",
                  "custom": "Custom"}
# The custom settings and their ranges (light keys flicker_<name>).
FLICKER_RANGES = {"speed": (0.1, 12.0), "brightness": (0.0, 1.0), "reach": (0.0, 0.5), "irregularity": (0.0, 1.0)}


def _f(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def flicker_profile(cfg: Mapping[str, Any]) -> FlickerProfile | None:
    """A light's flicker from its settings (a scene light, or a LightSource's config); None when steady.

    A named preset is used as it is. "custom" (or no preset: settings from before presets) takes the light's
    own values; older settings keep their meaning: ``flicker_amount`` for both brightness and reach,
    ``flicker_intensity`` for brightness, ``flicker_radius_px`` for reach (over ``radius``).
    """
    if not bool(cfg.get("flicker_enabled", False)):
        return None
    preset = str(cfg.get("flicker_preset") or "custom")
    if preset == "steady":
        return None
    if preset in FLICKER_PRESETS:
        return FLICKER_PRESETS[preset]
    amount = max(0.0, min(1.0, _f(cfg.get("flicker_amount"), 0.0)))
    brightness = cfg.get("flicker_brightness")
    if brightness is None:
        brightness = cfg.get("flicker_intensity") if cfg.get("flicker_intensity") is not None else amount
    reach = cfg.get("flicker_reach")
    if reach is None:
        radius_px, radius = cfg.get("flicker_radius_px"), _f(cfg.get("radius"), 0.0)
        reach = _f(radius_px, 0.0) / radius if radius_px is not None and radius > 0 else amount
    irregularity = max(0.0, min(1.0, _f(cfg.get("flicker_irregularity"), 0.5)))
    return FlickerProfile(speed=max(0.0, min(12.0, _f(cfg.get("flicker_speed"), 5.0))),
                          brightness=max(0.0, min(1.0, _f(brightness, 0.0))), reach=max(0.0, min(0.5, _f(reach, 0.0))),
                          irregularity=irregularity, flares=0.4 * irregularity)


def flicker_strength(cfg: Mapping[str, Any]) -> float:
    """The light's strength multiplier on its flicker (1: as the preset is)."""
    return max(0.0, min(3.0, _f(cfg.get("flicker_strength"), 1.0)))


def _knot(seed: int, octave: int, i: int) -> float:
    x = (i * 668265263 + seed * 374761393 + octave * 1442695041) & 0xFFFFFFFF
    x ^= x >> 13
    x = (x * 1274126177) & 0xFFFFFFFF
    x ^= x >> 16
    return (x / 0xFFFFFFFF) * 2.0 - 1.0


def _smooth_noise(seed: int, octave: int, t: float) -> float:
    """Smooth random wandering through random points (Catmull-Rom): no pause at each point, unlike easing."""
    i = math.floor(t)
    f = t - i
    p0, p1, p2, p3 = (_knot(seed, octave, i + k) for k in (-1, 0, 1, 2))
    value = 0.5 * (2 * p1 + (-p0 + p2) * f + (2 * p0 - 5 * p1 + 4 * p2 - p3) * f * f + (-p0 + 3 * p1 - 3 * p2 + p3) * f ** 3)
    return max(-1.0, min(1.0, value))


def _layered(seed: int, t: float, irregularity: float) -> float:
    """Several wanderings at unrelated speeds: more irregular, the more the faster ones count."""
    weights = (1.0, 0.55 * irregularity, 0.32 * irregularity)
    total = sum(w * _smooth_noise(seed, k, t * rate) for k, (w, rate) in enumerate(zip(weights, (1.0, 2.31, 5.17))))
    return total / sum(weights)


def _dip(seed: int, t: float, depth: float, reduced: bool) -> float:
    """A faulty lamp: mostly 1.0; now and then one to three short drop-outs within a second (never faster than
    three a second: no strobing), each a quick smooth dip, not a hard cut. Reduced: one soft, shallow dip."""
    window = math.floor(t / 1.2)  # about one chance every 1.2 s
    if _knot(seed, 13, window) * 0.5 + 0.5 > 0.25 * depth:
        return 1.0
    u = t - window * 1.2  # seconds into the window
    flicks = 1 if reduced else 1 + int((_knot(seed, 14, window) * 0.5 + 0.5) * 3) % 3
    level = 1.0
    for k in range(flicks):
        at = 0.15 + 0.36 * k + 0.08 * _knot(seed, 15, window * 7 + k)  # irregular spacing, >= 1/3 s apart
        width = 0.18 if reduced else 0.07 + 0.05 * (_knot(seed, 16, window * 7 + k) * 0.5 + 0.5)
        x = (u - at) / width
        if -1.0 < x < 1.0:
            low = 0.65 if reduced else 0.12 + 0.35 * (_knot(seed, 17, window * 7 + k) * 0.5 + 0.5)
            level = min(level, 1.0 - (1.0 - low) * (0.5 + 0.5 * math.cos(math.pi * x)))
    return level


def flicker_sample(profile: FlickerProfile, seed: int, time_s: float, strength: float = 1.0,
                   reduced: bool = False) -> tuple[float, float]:
    """(brightness factor, reach factor) of a flickering light at ``time_s``: smooth in time, reproducible
    for a seed, and different for different seeds (two torches don't flicker together)."""
    if reduced:  # calmer lights (an accessibility setting): gentler wavering, no stutter
        strength *= 0.4
    t = float(time_s) * profile.speed + (seed % 997) * 3.71
    wave = _layered(seed, t, profile.irregularity)
    flare = max(0.0, (_smooth_noise(seed, 11, t * 0.35) - 0.45) / 0.55) ** 2
    brightness = 1.0 + strength * (profile.brightness * wave + 0.5 * profile.flares * flare)
    if profile.dips > 0:
        brightness *= _dip(seed, float(time_s), min(1.0, profile.dips * max(0.3, strength)), reduced)
    reach = 1.0 + strength * profile.reach * (0.8 * _smooth_noise(seed, 7, t * 0.45) + 0.2 * wave)
    return max(0.0, brightness), max(0.2, reach)


def flicker_state(light: Any, base_radius: float, base_color: tuple[int, int, int, int],
                  settings: Mapping[str, Any], seed: int) -> _FlickerLightState:
    """The flicker state the light manager animates, from a light's settings (static or dynamic)."""
    from .types import _FlickerLightState  # noqa: PLC0415

    radius_px, intensity = settings.get("flicker_radius_px"), settings.get("flicker_intensity")
    return _FlickerLightState(
        light=light, base_radius=float(base_radius), base_color=base_color, noise=FlickerNoise(seed),
        speed=_f(settings.get("flicker_speed"), 1.0), amount=_f(settings.get("flicker_amount"), 0.0),
        radius_px=None if radius_px is None else _f(radius_px, 0.0),
        intensity=None if intensity is None else _f(intensity, 0.0),
        profile=flicker_profile({**settings, "flicker_enabled": True, "radius": base_radius}),
        seed=int(seed), strength=flicker_strength(settings))


def set_light_colour(light: Any, rgb: tuple[int, int, int]) -> None:
    """Change a light's colour (brightness). Arcade's Light keeps it private and only re-reads it when told."""
    if hasattr(light, "_color"):
        setattr(light, "_color", rgb)
        layer = getattr(light, "_light_layer", None)
        if layer is not None:
            setattr(layer, "_rebuild", True)
    elif hasattr(light, "color"):
        setattr(light, "color", rgb)


def apply_flicker(state: _FlickerLightState, time_s: float, reduced: bool = False) -> None:
    """Move a flickering light to how it looks at ``time_s`` (from its base, so stopping leaves no trace)."""
    light = state.light
    r, g, b, a = state.base_color
    if state.profile is None:  # a caller from before profiles: the original noise
        radius, colour = apply_light_flicker(base_radius=state.base_radius, base_color=(r, g, b, a), noise=state.noise,
                                             time_s=time_s, speed=state.speed, amount=state.amount,
                                             radius_px=state.radius_px, intensity=state.intensity)
        if hasattr(light, "radius"):
            light.radius = radius
        set_light_colour(light, (colour[0], colour[1], colour[2]))
        return
    brightness, reach = flicker_sample(state.profile, state.seed, time_s, state.strength, reduced)
    if hasattr(light, "radius"):
        light.radius = max(0.0, float(state.base_radius) * reach)

    def scaled(c: int) -> int:
        return int(round(max(0.0, min(255.0, c * brightness))))

    set_light_colour(light, (scaled(r), scaled(g), scaled(b)))


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
