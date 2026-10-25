"""A scene's HD-2D settings (``settings.hd2d``), validated. Positions are Mesh pixels like everything else in a
scene (x east, y north); 32 px is one metre in the 3D world.

    "settings": {"hd2d": {
        "structures": [{"model": "assets/models/stone_outpost.glb", "x": 384, "y": 256, "elevation": 0,
                        "rotation": 0, "scale": 1.0}],
        "ground": {"texture": "assets/textures/grass.png", "from": [0, 0], "to": [768, 512], "elevation": 0},
        "camera": {"pitch": 32, "fov": 30, "distance": 15, "ortho": false, "follow": "player", "height": 0.8},
        "sun": [-0.45, -0.55, 0.7], "ambient": 0.55
    }}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

PIXELS_PER_METRE = 32.0


class Hd2dSettingsError(ValueError):
    """A scene's HD-2D settings are unusable; the message names the key."""


@dataclass(frozen=True)
class Structure:
    model: str  # project-relative path to a .glb
    x: float
    y: float
    elevation: float = 0.0
    rotation: float = 0.0  # degrees, about the vertical axis
    scale: float = 1.0


@dataclass(frozen=True)
class Ground:
    texture: str | None
    lo: tuple[float, float]
    hi: tuple[float, float]
    elevation: float = 0.0


@dataclass(frozen=True)
class CameraSettings:
    pitch: float = 32.0  # degrees below horizontal
    fov: float = 30.0  # vertical field of view, degrees
    distance: float = 15.0  # metres from the target
    ortho: bool = False
    follow: str = "player"  # entity tag the camera follows
    height: float = 0.8  # metres above the followed entity's feet


@dataclass(frozen=True)
class Hd2dSettings:
    structures: tuple[Structure, ...] = ()
    ground: Ground | None = None
    camera: CameraSettings = field(default_factory=CameraSettings)
    sun: tuple[float, float, float] = (-0.45, -0.55, 0.70)
    ambient: float = 0.55


def _number(block: dict, key: str, where: str, default: float, lo: float | None = None, hi: float | None = None) -> float:
    value = block.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise Hd2dSettingsError(f"{where}.{key} must be a number (got {value!r})")
    if (lo is not None and value < lo) or (hi is not None and value > hi):
        raise Hd2dSettingsError(f"{where}.{key} must be between {lo} and {hi} (got {value})")
    return float(value)


def _pair(block: dict, key: str, where: str, default: tuple[float, float]) -> tuple[float, float]:
    value = block.get(key, default)
    if not (isinstance(value, (list, tuple)) and len(value) == 2 and all(isinstance(v, (int, float)) for v in value)):
        raise Hd2dSettingsError(f"{where}.{key} must be [x, y] (got {value!r})")
    return float(value[0]), float(value[1])


def parse_hd2d(raw: Any, *, map_size_px: tuple[float, float] | None = None) -> Hd2dSettings:
    """``settings.hd2d`` as Hd2dSettings. Raises Hd2dSettingsError naming the bad key."""
    if not isinstance(raw, dict):
        raise Hd2dSettingsError(f"settings.hd2d must be an object (got {type(raw).__name__})")
    unknown = set(raw) - {"structures", "ground", "camera", "sun", "ambient"}
    if unknown:
        raise Hd2dSettingsError(f"settings.hd2d has unknown keys: {', '.join(sorted(unknown))}")
    structures = []
    for i, item in enumerate(raw.get("structures", []) or []):
        where = f"settings.hd2d.structures[{i}]"
        if not isinstance(item, dict):
            raise Hd2dSettingsError(f"{where} must be an object")
        model = item.get("model")
        if not isinstance(model, str) or not model.lower().endswith(".glb"):
            raise Hd2dSettingsError(f"{where}.model must be a project-relative .glb path (got {model!r})")
        structures.append(Structure(model, _number(item, "x", where, 0.0), _number(item, "y", where, 0.0),
                                    _number(item, "elevation", where, 0.0), _number(item, "rotation", where, 0.0),
                                    _number(item, "scale", where, 1.0, 0.01, 100.0)))
    ground = None
    if raw.get("ground") is not None:
        g = raw["ground"]
        if not isinstance(g, dict):
            raise Hd2dSettingsError("settings.hd2d.ground must be an object")
        texture = g.get("texture")
        if texture is not None and not isinstance(texture, str):
            raise Hd2dSettingsError("settings.hd2d.ground.texture must be a project-relative image path")
        default_hi = map_size_px or (32.0 * 24, 32.0 * 16)
        ground = Ground(texture, _pair(g, "from", "settings.hd2d.ground", (0.0, 0.0)),
                        _pair(g, "to", "settings.hd2d.ground", default_hi),
                        _number(g, "elevation", "settings.hd2d.ground", 0.0))
    c = raw.get("camera", {}) or {}
    if not isinstance(c, dict):
        raise Hd2dSettingsError("settings.hd2d.camera must be an object")
    where = "settings.hd2d.camera"
    camera = CameraSettings(_number(c, "pitch", where, 32.0, 5.0, 89.0), _number(c, "fov", where, 30.0, 5.0, 120.0),
                            _number(c, "distance", where, 15.0, 1.0, 500.0), bool(c.get("ortho", False)),
                            str(c.get("follow", "player")), _number(c, "height", where, 0.8, -10.0, 50.0))
    sun = raw.get("sun", [-0.45, -0.55, 0.70])
    if not (isinstance(sun, (list, tuple)) and len(sun) == 3 and all(isinstance(v, (int, float)) for v in sun)
            and any(sun)):
        raise Hd2dSettingsError(f"settings.hd2d.sun must be a direction [x, y, z] (got {sun!r})")
    return Hd2dSettings(tuple(structures), ground, camera, (float(sun[0]), float(sun[1]), float(sun[2])),
                        _number(raw, "ambient", "settings.hd2d", 0.55, 0.0, 1.0))
