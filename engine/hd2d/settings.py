"""A scene's HD-2D settings (``settings.hd2d``), validated. Positions are Mesh pixels like everything else in a
scene (x east, y north); 32 px is one metre in the 3D world.

    "settings": {"hd2d": {
        "structures": [{"id": "outpost", "model": "assets/models/stone_outpost.glb", "x": 384, "y": 256, "elevation": 0,
                        "rotation": 0, "scale": 1.0}],
        "ground": {"texture": "assets/textures/grass.png", "from": [0, 0], "to": [768, 512], "elevation": 0},
        "camera": {"pitch": 32, "fov": 30, "distance": 15, "ortho": false, "follow": "player", "height": 0.8},
        "sun": [-0.45, -0.55, 0.7], "ambient": 0.55,
        "shadows": true, "shadow_resolution": 2048
    }}

``sun`` may also be ``{"direction": [x, y, z], "color": "#ffe8c0", "intensity": 1.0}`` (a direction alone is white
sunlight of intensity 1). Lamps are the scene's ordinary ``lights`` (as 2D rooms use them; ``parse_scene_lights``),
with an optional HD-2D ``elevation``; a light of ``"type": "ambient"`` tints the ambient light. The room's
``lighting_shadow_softness`` (sharp / soft / softer) and ``lighting_shadow_strength`` shape HD-2D shadows as they
shape 2D ones.
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
    id: str = ""  # stable within the scene ("structure<index>" when not given): names its floors ("outpost/deck")


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


Rgb = tuple[float, float, float]
LAMP_HEIGHT_PX = 48.0  # a lamp without an elevation hangs 1.5 m up
MAX_LIGHTS = 8  # lamps lit per room (the shader's budget)
MAX_SHADOW_LIGHTS = 2  # of them, casting shadows (each a 6-face shadow map)


@dataclass(frozen=True)
class PointLight:
    x: float  # px
    y: float
    elevation: float  # px above the ground
    radius: float  # px: its light ends here
    color: Rgb  # 0..1
    intensity: float = 1.0
    shadows: bool = True


@dataclass(frozen=True)
class Hd2dSettings:
    structures: tuple[Structure, ...] = ()
    ground: Ground | None = None
    camera: CameraSettings = field(default_factory=CameraSettings)
    sun: tuple[float, float, float] = (-0.45, -0.55, 0.70)  # towards the sun
    ambient: float = 0.55
    sun_color: Rgb = (1.0, 1.0, 1.0)
    sun_intensity: float = 1.0
    ambient_color: Rgb = (1.0, 1.0, 1.0)
    shadows: bool = True
    shadow_resolution: int = 2048
    shadow_softness: str = "sharp"  # the room's lighting_shadow_softness
    shadow_strength: float = 1.0  # the room's lighting_shadow_strength: 0 none .. 1 full
    lights: tuple[PointLight, ...] = ()


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
    unknown = set(raw) - {"structures", "ground", "camera", "sun", "ambient", "shadows", "shadow_resolution"}
    if unknown:
        raise Hd2dSettingsError(f"settings.hd2d has unknown keys: {', '.join(sorted(unknown))}")
    structures = []
    seen: set[str] = set()
    for i, item in enumerate(raw.get("structures", []) or []):
        where = f"settings.hd2d.structures[{i}]"
        if not isinstance(item, dict):
            raise Hd2dSettingsError(f"{where} must be an object")
        extra = set(item) - {"id", "model", "x", "y", "elevation", "rotation", "scale"}
        if extra:
            raise Hd2dSettingsError(f"{where} has unknown keys: {', '.join(sorted(extra))}")
        model = item.get("model")
        if not isinstance(model, str) or not model.lower().endswith(".glb"):
            raise Hd2dSettingsError(f"{where}.model must be a project-relative .glb path (got {model!r})")
        sid = item.get("id", f"structure{i}")
        if not isinstance(sid, str) or not sid.strip() or "/" in sid:
            raise Hd2dSettingsError(f"{where}.id must be a non-empty name without '/' (got {sid!r})")
        if sid in seen:
            raise Hd2dSettingsError(f"{where}.id '{sid}' is used twice; structure ids must be unique in a scene")
        seen.add(sid)
        structures.append(Structure(model, _number(item, "x", where, 0.0), _number(item, "y", where, 0.0),
                                    _number(item, "elevation", where, 0.0), _number(item, "rotation", where, 0.0),
                                    _number(item, "scale", where, 1.0, 0.01, 100.0), sid))
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
    sun_raw = raw.get("sun", [-0.45, -0.55, 0.70])
    sun_block = sun_raw if isinstance(sun_raw, dict) else {"direction": sun_raw}
    extra = set(sun_block) - {"direction", "color", "intensity"}
    if extra:
        raise Hd2dSettingsError(f"settings.hd2d.sun has unknown keys: {', '.join(sorted(extra))}")
    sun = sun_block.get("direction", [-0.45, -0.55, 0.70])
    if not (isinstance(sun, (list, tuple)) and len(sun) == 3 and all(isinstance(v, (int, float)) for v in sun)
            and any(sun)):
        raise Hd2dSettingsError(f"settings.hd2d.sun must be a direction [x, y, z] (got {sun!r})")
    sun_color = rgb(sun_block.get("color", (255, 255, 255)))
    if sun_color is None:
        raise Hd2dSettingsError(f"settings.hd2d.sun.color must be a colour (got {sun_block.get('color')!r})")
    shadows = raw.get("shadows", True)
    if not isinstance(shadows, bool):
        raise Hd2dSettingsError(f"settings.hd2d.shadows must be true or false (got {shadows!r})")
    resolution = raw.get("shadow_resolution", 2048)
    if resolution not in (1024, 2048, 4096):
        raise Hd2dSettingsError(f"settings.hd2d.shadow_resolution must be 1024, 2048 or 4096 (got {resolution!r})")
    return Hd2dSettings(tuple(structures), ground, camera, (float(sun[0]), float(sun[1]), float(sun[2])),
                        _number(raw, "ambient", "settings.hd2d", 0.55, 0.0, 1.0), sun_color,
                        _number(sun_block, "intensity", "settings.hd2d.sun", 1.0, 0.0, 10.0), shadows=shadows,
                        shadow_resolution=int(resolution))


def rgb(value: Any) -> Rgb | None:
    """A colour as Mesh's lights write it ("#rrggbb", "#rrggbbaa" or [r, g, b(, a)] in 0..255) as 0..1 floats."""
    if isinstance(value, str) and value.startswith("#") and len(value) in (7, 9):
        try:
            return (int(value[1:3], 16) / 255, int(value[3:5], 16) / 255, int(value[5:7], 16) / 255)
        except ValueError:
            return None
    if isinstance(value, (list, tuple)) and len(value) >= 3 and all(isinstance(v, (int, float)) for v in value[:3]):
        return (min(max(value[0], 0), 255) / 255, min(max(value[1], 0), 255) / 255, min(max(value[2], 0), 255) / 255)
    return None


def parse_scene_lights(lights: Any, room: Any) -> dict[str, Any]:
    """The scene's ordinary ``lights`` and the room's shadow settings, as Hd2dSettings fields. Read as leniently
    as the 2D lighting reads them (a light it can't use is skipped, as there), keeping the first MAX_LIGHTS
    enabled lamps and letting the first MAX_SHADOW_LIGHTS that ask for shadows (the 2D default) cast them."""
    out: dict[str, Any] = {}
    lamps: list[PointLight] = []
    shadowed = 0
    for cfg in lights if isinstance(lights, list) else []:
        if not isinstance(cfg, dict) or cfg.get("enabled", True) is False:
            continue
        colour = rgb(cfg.get("color_rgba", cfg.get("color", (255, 255, 255)))) or (1.0, 1.0, 1.0)
        if cfg.get("type") == "ambient":
            out["ambient_color"] = colour
            continue
        try:
            x, y, radius = float(cfg.get("x", 0.0)), float(cfg.get("y", 0.0)), float(cfg.get("radius", 100.0))
            elevation, intensity = float(cfg.get("elevation", LAMP_HEIGHT_PX)), float(cfg.get("intensity", 1.0))
        except (TypeError, ValueError):
            continue
        if radius <= 0 or len(lamps) >= MAX_LIGHTS:
            continue
        casts = cfg.get("shadows", True) is not False and shadowed < MAX_SHADOW_LIGHTS
        shadowed += casts
        lamps.append(PointLight(x, y, elevation, radius, colour, max(0.0, intensity), casts))
    out["lights"] = tuple(lamps)
    room = room if isinstance(room, dict) else {}
    softness = room.get("lighting_shadow_softness", "sharp")
    out["shadow_softness"] = softness if softness in ("sharp", "soft", "softer") else "sharp"
    strength = room.get("lighting_shadow_strength", 1.0)
    out["shadow_strength"] = min(max(float(strength), 0.0), 1.0) if isinstance(strength, (int, float)) else 1.0
    return out
