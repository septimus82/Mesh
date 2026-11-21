"""An HD-2D room's atmospheric depth (M17-L4-3): distant scenery fades toward a haze colour with its distance from the
camera, drawn by the renderer's final composite (engine.hd2d.composite) in the game and in Mesh Studio's editing view
alike.

    "settings": {"hd2d": {"haze": {"preset": "daytime", "strength": 0.2, "color": "#9fb0c4", "start": 4, "falloff": 30}}}

- No ``haze`` block (every room made before L4-3, and every new room): **off**. The picture is exactly what it was.
- ``preset`` (required): ``daytime`` (subtle, cool) or ``evening`` (a little stronger, warm) (``PRESETS``). Off is no
  block (``project_ops.set_hd2d_haze(preset="off")`` removes it).
- ``strength`` (0-0.5): how far the most distant things move toward the haze colour (0: the original picture, the
  composite not run for it). Capped at half so distance never hides what's there.
- ``color`` ("#rrggbb"): the haze's colour in full daylight. It is **lit by the room's own light** (``light_of``: its
  ambient light plus its sun, the sun's share fading as it nears the horizon; no lamps), so the same haze is dim at
  night and takes the evening sun's colour: it never glows on its own.
- ``start`` (m, 0-40): how far beyond the camera's focus the haze begins. The focus is the followed character in play
  (the point the view looks at in Studio, or with nobody followed), as the depth of field's. In play the haze never
  starts within the character's own depth (plus ``CHARACTER_MARGIN``), whatever ``start`` says, so the player and
  what stands right behind them keep their contrast.
- ``falloff`` (m, 1-80): how far beyond the start it takes to reach (nearly: 95%) its full strength. The curve has no
  corner at the start (``amount``): no visible edge where the haze begins.
Only the values that differ from the preset's are stored.

How far each thing is: its own depth, from the depth the world was drawn with (never its height on screen), measured
along the camera's view axis (the depth of field's linearisation). So a tree standing in front of the far meadow
keeps the tree's distance, not the meadow's. Water is drawn without depth (it's see-through), so it hazes as its bed;
falling weather, embers and smoke haze as what is behind them. Where nothing was drawn (the room's ``sky``: an
interior's darkness, or the colour round a room in Studio) is left as it is: it is the room's backdrop, already the
colour the creator chose for "beyond", not distant scenery. The mix
is in linear light, before the colour grade (the grade treats the hazed scene as it treats the rest). Studio's lines,
Mesh's HUD, menus and dialogue are drawn after the composite: never hazed.

It costs no pass, texture or target of its own (it is part of the final composite). Software rendering runs it too:
measured on Mesa llvmpipe at 1280x720, +0.8 ms a frame (25 ms) and +0.6 ms for the pass over a plain blit, unlike the
depth of field (bypassed there). A driver that refuses the composite's program gives the original picture, the reason
kept (``Hd2dRenderer.composite_unavailable``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

Rgb = tuple[float, float, float]
CHARACTER_MARGIN = 1.0  # m beyond the followed character's own depth the haze can't start within
FULL = 3.0  # amount's exponent: at start + falloff the haze is at 1 - e^-3 (95%) of its strength


@dataclass(frozen=True)
class Look:
    """A preset's values."""
    label: str
    strength: float
    color: Rgb  # 0-1, sRGB as the room's colours are written
    start: float
    falloff: float


PRESETS: dict[str, Look] = {
    # tuned on Lakeside (M17-L4-3 evidence): the far meadow softens and cools a little, the foreground untouched; the
    # start keeps a villager a few metres behind the player readable (dark pixels lift most: the mix is in linear light)
    "daytime": Look("Daytime", 0.25, (0x9f / 255, 0xb0 / 255, 0xc4 / 255), 4.0, 30.0),
    "evening": Look("Evening", 0.3, (0xd4 / 255, 0xb4 / 255, 0xa4 / 255), 4.0, 24.0),
}
STRENGTH = (0.0, 0.5)
START = (0.0, 40.0)
FALLOFF = (1.0, 80.0)


class HazeError(ValueError):
    """A room's ``settings.hd2d.haze`` can't be used."""


@dataclass(frozen=True)
class Haze:
    """``settings.hd2d.haze``, read: the preset, and each value (None: the preset's)."""
    preset: str
    strength: float | None = None
    color: Rgb | None = None
    start: float | None = None
    falloff: float | None = None

    @property
    def look(self) -> Look:
        return PRESETS[self.preset]

    @property
    def values(self) -> Look:
        """Every value in play: the room's own, else its preset's."""
        k = self.look
        return Look(k.label, k.strength if self.strength is None else self.strength,
                    k.color if self.color is None else self.color, k.start if self.start is None else self.start,
                    k.falloff if self.falloff is None else self.falloff)

    @property
    def active(self) -> bool:
        """Whether it changes the picture at all (strength 0: the original; the composite not run for it)."""
        return self.values.strength > 0.0


def amount(distance: float, onset: float, falloff: float, strength: float) -> float:
    """How far (0-``strength``) a pixel ``distance`` m away along the view axis moves toward the haze colour, the
    haze beginning ``onset`` m away: what the composite computes (no corner at the onset, 95% at onset + falloff)."""
    x = max(0.0, distance - onset) / falloff
    return strength * (1.0 - math.exp(-FULL * x * x))


def onset(focus: float, start: float, band: float | None) -> float:
    """Where the haze begins (m along the view axis): ``start`` beyond the ``focus``; in play (``band``: half the
    followed character's own depth) never within the character's depth plus ``CHARACTER_MARGIN``."""
    return focus + (start if band is None else max(start, band + CHARACTER_MARGIN))


SUN_FADE = 4.0  # the sun's share of the haze's light: full from sin(elevation) 1/4 (14.5 degrees) up, none below 0


def light_of(ambient: float, ambient_color: Rgb, sun: tuple[float, float, float], sun_intensity: float,
             sun_color: Rgb) -> Rgb:
    """What lights the haze: the room's ambient light plus its sun, as engine.hd2d.lighting's ``light_at`` lights a
    surface facing the sun (air has no surface to turn away), the sun's share fading out as it nears the horizon
    (``SUN_FADE``); no lamps. ``sun``: the direction toward it (normalised here). Each channel at most 1."""
    n = math.sqrt(sum(c * c for c in sun)) or 1.0
    up = min(1.0, max(0.0, sun[2] / n) * SUN_FADE)

    def channel(i: int) -> float:
        return min(1.0, ambient_color[i] * ambient + sun_color[i] * sun_intensity * (1.0 - ambient) * up)

    return (channel(0), channel(1), channel(2))


def linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def shown(haze: Haze, light: Rgb) -> Rgb:
    """The haze colour as the scene shows it (sRGB 0-1): its colour, lit."""
    color = haze.values.color
    return (min(1.0, color[0] * light[0]), min(1.0, color[1] * light[1]), min(1.0, color[2] * light[2]))


def uniforms(haze: Haze, light: Rgb) -> dict[str, Any]:
    """The composite's haze values that change only with the room's settings (the onset is the frame's)."""
    v = haze.values
    lit = shown(haze, light)
    return {"u_haze": v.strength, "u_haze_color": (linear(lit[0]), linear(lit[1]), linear(lit[2])),
            "u_haze_falloff": v.falloff}


def _number(raw: dict[str, Any], key: str, lo: float, hi: float, where: str) -> float:
    value = raw[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) \
            or not lo <= value <= hi:
        raise HazeError(f"{where}.{key} must be a number from {lo:g} to {hi:g} (got {value!r})")
    return float(value)


def parse_haze(raw: Any) -> Haze | None:
    """``settings.hd2d.haze`` as Haze (None: no block, off). Raises HazeError naming the bad key."""
    if raw is None:
        return None
    where = "settings.hd2d.haze"
    if not isinstance(raw, dict):
        raise HazeError(f"{where} must be an object (got {type(raw).__name__})")
    unknown = set(raw) - {"preset", "strength", "color", "start", "falloff"}
    if unknown:
        raise HazeError(f"{where} has unknown keys: {', '.join(sorted(map(str, unknown)))}")
    preset = raw.get("preset")
    if not isinstance(preset, str) or preset not in PRESETS:
        raise HazeError(f"{where}.preset must be one of {', '.join(PRESETS)} (got {preset!r})")
    color = None
    if "color" in raw:
        from engine.hd2d.settings import rgb  # noqa: PLC0415

        color = rgb(raw["color"]) if isinstance(raw["color"], (str, list, tuple)) else None
        if color is None:
            raise HazeError(f"{where}.color must be a colour like #9fb0c4 (got {raw['color']!r})")
        color = (color[0], color[1], color[2])
    return Haze(preset,
                _number(raw, "strength", *STRENGTH, where) if "strength" in raw else None, color,
                _number(raw, "start", *START, where) if "start" in raw else None,
                _number(raw, "falloff", *FALLOFF, where) if "falloff" in raw else None)


def hex_color(c: Rgb) -> str:
    return "#" + "".join(f"{round(max(0.0, min(1.0, v)) * 255):02x}" for v in c)


def stored(haze: Haze | None) -> dict[str, Any] | None:
    """What the scene keeps: None (no key: off), else the preset and only the values that differ from its own."""
    if haze is None:
        return None
    k, out = haze.look, {"preset": haze.preset}
    for key in ("strength", "start", "falloff"):
        value = getattr(haze, key)
        if value is not None and value != getattr(k, key):
            out[key] = value
    if haze.color is not None and hex_color(haze.color) != hex_color(k.color):
        out["color"] = hex_color(haze.color)
    return out


__all__ = ["CHARACTER_MARGIN", "PRESETS", "Haze", "HazeError", "Look", "amount", "hex_color", "light_of", "onset",
           "parse_haze", "shown", "stored", "uniforms"]
