"""A campfire (Milestone 23B): an HD-2D object with the ``Campfire`` behaviour (Mesh Studio: Objects > Campfire).

Built from what is there, no new particle framework:

- its **logs and flames** are scatter sprites (``engine.hd2d.scatter``'s hidden ``campfire`` and ``campfire_flame``
  assets: Milestone 20E's animated, wind-bent, glowing billboards, depth-tested as any decoration), drawn by a scatter
  layer of their own whose motion is always on (a fire flickers in a room whose grass is still);
- its **embers, sparks and smoke** are ``engine.scene_particles``' world-space particles (kinds 3 and 4), anchored at
  the fires: stateless and seeded, one draw each for all the room's fires;
- its **light** is an HD-2D point light (``engine.hd2d.lighting``'s ``extra_lamps``), warm, flickering by the time
  alone (the same time, the same flicker), with no shadow map of its own.

Settings (``behaviour_config.Campfire``; Studio and AI: ``project_ops.set_campfire``): ``enabled`` (off: no flame,
embers, smoke or light, only the cold logs), ``size`` (the flames, 0.5-1.5), ``smoke``, ``light`` (its strength,
0-3) and ``light_radius`` (px). A 2D room draws none of it (its objects have no logs to show)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

PX_PER_M = 32.0
MAX_FIRES = 16  # whose embers and smoke are drawn at once (the particle shader's anchors: the nearest the camera)
COLOUR = (1.0, 0.56, 0.24)  # the light's: firelight
STRENGTH = 1.8  # its intensity at strength 1 (the HD-2D template's lamps: 1.6)
LIGHT_UP = 0.6  # m: the light stands this far above the logs (in the flames)
DEFAULTS = {"enabled": True, "size": 1.0, "smoke": True, "light": 1.0, "light_radius": 192.0}
_KEYS = set(DEFAULTS)


class FireError(ValueError):
    """Campfire settings that can't be used."""


@dataclass(frozen=True)
class Fire:
    enabled: bool = True
    size: float = 1.0  # the flames (times their drawn size)
    smoke: bool = True
    light: float = 1.0  # strength
    light_radius: float = 192.0  # px


def parse_fire(raw: Any) -> Fire:
    """``behaviour_config.Campfire`` checked (missing keys: ``DEFAULTS``)."""
    if not isinstance(raw, dict):
        raise FireError(f"A campfire's settings are an object (got {type(raw).__name__}).")
    unknown = set(raw) - _KEYS
    if unknown:
        raise FireError(f"A campfire has no setting {sorted(unknown)[0]!r} (it has: {', '.join(DEFAULTS)}).")
    v = {**DEFAULTS, **raw}
    for key in ("enabled", "smoke"):
        if not isinstance(v[key], bool):
            raise FireError(f"A campfire's {key} is true or false (got {v[key]!r}).")

    def number(key: str, lo: float, hi: float) -> float:
        value = v[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not lo <= value <= hi:
            raise FireError(f"A campfire's {key} is a number from {lo:g} to {hi:g} (got {value!r}).")
        return float(value)

    return Fire(v["enabled"], number("size", 0.5, 1.5), v["smoke"], number("light", 0.0, 3.0),
                number("light_radius", 32.0, 640.0))


# --- a room's fires: registry (a window attribute; reset on every room load) --------------------------------------
@dataclass
class Hearth:
    """A campfire in the room as its behaviour sees it: its object (for where it is) and its settings."""
    entity: Any
    fire: Fire

    def place(self) -> tuple[float, float, float]:
        """Where its logs stand: x, y (px) and its elevation (px; 0: none given)."""
        e = self.entity
        level = (getattr(e, "mesh_entity_data", None) or {}).get("elevation", 0.0)
        level = float(level) if isinstance(level, (int, float)) and not isinstance(level, bool) else 0.0
        return float(e.center_x), float(e.center_y), level


def reset(window: Any) -> None:
    """A room is loading: its campfires register as their behaviours start."""
    window.campfires = []


def register(window: Any, entity: Any, fire: Fire) -> None:
    hearths = getattr(window, "campfires", None)
    if hearths is None:
        hearths = window.campfires = []
    hearths[:] = [h for h in hearths if h.entity is not entity] + [Hearth(entity, fire)]


def fires_of(window: Any) -> list[Hearth]:
    """The room's campfires there now (their "Show when" flags, as water's): every one (their logs and flames have
    no limit; their lights and particles are the nearest the camera's)."""
    from engine.water import active  # noqa: PLC0415

    return [h for h in (getattr(window, "campfires", None) or []) if active(window, h.entity)]


def base(hearth: Hearth, ground: Any = None) -> float:
    """The height (px) its logs stand at: its elevation if it has one (Mesh Studio gives an object placed on a floor,
    a bridge or a hill the height it stands at), else the ground's there (``ground(x, y)``, px), else 0."""
    x, y, level = hearth.place()
    if level or ground is None:
        return level
    return float(ground(x, y))


def flicker(time: float, x: float, y: float) -> float:
    """How bright a fire is now (about 0.8-1.1): a few incommensurate waves, out of step fire to fire by where it
    stands; the same time, the same flicker."""
    s = (x * 0.137 + y * 0.071) % 7.0
    w = (math.sin(time * 7.3 + s) * 0.5 + math.sin(time * 11.9 + s * 2.1) * 0.3
         + math.sin(time * 2.3 + s * 0.7) * 0.6 + math.sin(time * 23.0 + s * 3.7) * 0.15)
    return 0.95 + 0.1 * w / 1.55


def lamps(hearths: list[Hearth], time: float, ground: Any = None) -> list[Any]:
    """The lit fires' lights now (``engine.hd2d.settings.PointLight``: no shadow map), over where each stands
    (``base``; ``ground(x, y)``: the ground's height there, px)."""
    from engine.hd2d.settings import PointLight  # noqa: PLC0415

    out = []
    for h in hearths:
        f = h.fire
        if not f.enabled or f.light <= 0:
            continue
        x, y, _level = h.place()
        k = flicker(time, x, y)
        out.append(PointLight(x, y, base(h, ground) + LIGHT_UP * PX_PER_M * f.size, f.light_radius * (0.97 + 0.03 * k),
                              COLOUR, f.light * STRENGTH * k, shadows=False))
    return out
