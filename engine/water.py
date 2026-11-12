"""Lightweight water surfaces (Milestone 19A): puddles and ponds, drawn, not simulated.

A water surface is an object (an entity) with the ``WaterSurface`` behaviour: its place (x, y; in an HD-2D room
its ``elevation`` is the water's level) and its ``behaviour_config["WaterSurface"]`` (``parse_water``): a preset
("puddle" or "pond"), a size (px, like a trigger zone), and optionally its colour, opacity, shape, waves, whether rain
ripples it and whether it can be walked through. Studio and AI change it through ``project_ops.set_water``.

How it looks, all in one fragment shader, one instanced draw call for every water surface in the room:

- **On the pixel grid.** Waves, ripples and highlights are worked out per texel of the art's 32 px per metre, so the
  water reads as pixel art, not a smooth shader.
- **Movement.** Gentle waves (two slow sine trains across the surface), stronger on ponds.
- **Colour and depth.** The preset's or the creator's colour and opacity; a pond darkens towards its middle and has a
  light rim at its edge; a puddle stays thin and pale.
- **Reflection (HD-2D).** A cheap environmental reflection: the view ray is mirrored at the surface (bent by the
  waves) and marched a few steps through a copy of the frame drawn so far (colour and depth). Where it meets
  something on screen (the cottage, the bridge, a character) the water shows it; elsewhere the sky's colour. No
  second render of the scene. 2D rooms get the sky's tint and highlights only.
- **Rain ripples.** While the room's rain falls (and isn't kept off by something above the water: the rain's
  precipitation map, Stage 18B), rings start on the surface at a rate from the rain's density: a grid of cells, each
  starting rings at hashed places and times. Nothing comes back from the GPU's raindrops; the rings are as stable in
  the world as the surface.
- **Footsteps.** A character walking through water leaves a ring and a few splash pixels where each step lands
  (``WaterSurface`` behaviour, up to ``MAX_STEPS`` at once), and optionally a sound and a ``water_step`` event.

Depth: drawn after the room's structures and characters, depth-tested and not writing depth, blended. A ``WaterLayer``
owns its GPU objects (program, quad, instance buffer, the frame copy) and frees them in ``release`` (room change,
window close).

Milestone 19B, water that belongs to its place (the same pass and draw call; Stage 19A's "puddle" and "pond" keep their
look exactly, ``CLASSIC``):

- **Shapes.** ``shape`` "natural" is an irregular outline (``outline``: a few harmonics a ``seed`` picks, fitted inside
  the ellipse its size makes), and any shape can be turned (``rotation``). Footsteps, Studio's outline and picking use
  the same outline (``inside``, ``outline_points``); a blocking pond blocks the box round it as turned (``extent``).
- **The material** (presets "muddy_puddle", "natural_pond", "stone_pool"): from its shallow ``colour`` at the edge,
  where the ground beneath shows through, to its ``deep_colour`` as soon as its ``depth`` says; a bank round it
  (``shore`` "mud": wet ground, darkest at the water; "grass": an earth lip and reeds; "stone": a rim of whole stones,
  lit on their sunward side), ``shore_width`` px wide, drawn in the same quad, ragged per texel; the water lying a
  little below the ground, so near its far edge the bank's side shows (earth or stone courses) with its shadow on the
  water, which makes it read as set into the ground, not laid on it; a crisp waterline on its near edge; slow glints
  as many as its waves; ripples as strong as its ``ripples``. Its mirror takes the water's hue, stays under its colour
  and fades to the sky for what stands far from it.
- **Reflections cost** (the room's ``settings.hd2d.water_reflections``, ``REFLECTIONS``): the frame copy at full size,
  at half size (a quarter of the memory) or none (the sky's colour only).
"""

from __future__ import annotations

import functools
import math
import random
from array import array
from dataclasses import dataclass, replace
from typing import Any

from engine.hd2d.bloom import OUTPUTS
from engine.hd2d.lighting import LIGHTING_GLSL

PX_PER_M = 32.0
LIFT_M = 0.035  # the surface stands this far above its level: over the ground and paths (2 cm tall), not z-fighting
MAX_STEPS = 8  # footstep ripples alive at once (the oldest gives way)
MOUTH_BLEND_M = 1.5  # a river takes on the look of the pond it flows into over this (engine.hd2d.river.BLEND_M)
MAX_MOUTHS = 8  # rivers flowing into ponds a room's shaders hold (engine.hd2d.river.MAX_MOUTHS)
STEP_RIPPLE_S = 1.0  # how long a footstep's ring lasts
_KEYS = {"preset", "width", "height", "colour", "opacity", "shape", "waves", "rain_ripples", "walkable", "step_sound",
         "reflection", "rotation", "seed", "shore", "shore_width", "deep_colour", "depth", "ripples", "passable",
         "wade_depth"}
# R4B (#461): how characters may go into water (ponds and rivers alike), whatever it looks like or how deep its bed is
# carved: "auto" as before (a pond by its ``walkable``; a river waded up to half a metre deep), "wade" waded up to
# ``wade_depth`` m over the floor, "block" not entered at all (a bridge's deck above it stays dry)
PASSABLE = ("auto", "wade", "block")
WADE_DEPTH_M = (0.1, 1.5)  # a wade's depth limit: a tenth of a metre to a character's height (no swimming)
WADE_DEPTH_DEFAULT = 1.0
SHAPES = ("ellipse", "rect", "natural")
SHORES = ("none", "mud", "grass", "stone", "terrain")  # terrain: the sculpted ground is its shore (Milestone 20A)
CLASSIC = ("puddle", "pond")  # Stage 19A's look, kept exactly (older rooms; the negative controls)
LOOK_19B = ("shore", "shore_width", "deep_colour", "depth", "ripples")  # the material's settings (not CLASSIC's)
REFLECTIONS = ("full", "half", "sky")  # settings.hd2d.water_reflections: the frame copy at full or half size, or none


class WaterError(ValueError):
    """``WaterSurface`` settings that can't be used."""


@dataclass(frozen=True)
class Water:
    preset: str  # "puddle" | "pond"
    width: float  # px
    height: float  # px
    colour: tuple[float, float, float]  # 0..1
    opacity: float  # 0..1
    shape: str  # "ellipse" | "rect" (a rectangle with softened corners)
    waves: float  # 0..1: how much the surface moves
    reflection: float  # 0..1: how much it mirrors
    rain_ripples: bool
    walkable: bool  # False: it blocks movement (the object is made solid, with a box the water's size)
    step_sound: str  # a sound played on each step through it ("" none)
    rotation: float = 0.0  # degrees, anticlockwise
    seed: int = 1  # which irregular outline a "natural" shape has (and where a stone rim's stones lie)
    # Stage 19B's material (not the CLASSIC presets'): the bank round it, shallow to deep, ripple strength
    shore: str = "none"  # "mud" | "grass" | "stone": the bank's treatment
    shore_width: float = 0.0  # px: how far the bank reaches out from the water's edge
    deep_colour: tuple[float, float, float] = (0.0, 0.0, 0.0)  # its colour where deepest (colour: in the shallows)
    depth: float = 0.0  # 0..1: how soon it gets deep (and opaque) away from the edge
    ripples: float = 1.0  # 0..1: how strongly rain and footsteps ring it
    passable: str = "auto"  # PASSABLE (R4B): "auto" by ``walkable``
    wade_depth: float = WADE_DEPTH_DEFAULT  # m: the deepest it is waded, if passable is "wade"


PRESETS: dict[str, Water] = {
    "puddle": Water("puddle", 64.0, 40.0, (0.42, 0.50, 0.58), 0.62, "ellipse", 0.15, 0.85, True, True, ""),
    "pond": Water("pond", 224.0, 144.0, (0.16, 0.36, 0.42), 0.84, "ellipse", 0.6, 0.35, True, True, ""),
    "muddy_puddle": Water("muddy_puddle", 72.0, 44.0, (0.40, 0.37, 0.30), 0.80, "natural", 0.12, 0.6, True, True, "",
                          seed=3, shore="mud", shore_width=8.0, deep_colour=(0.24, 0.25, 0.24), depth=0.25),
    "natural_pond": Water("natural_pond", 224.0, 150.0, (0.30, 0.45, 0.38), 0.90, "natural", 0.45, 0.30, True, True,
                          "", seed=7, shore="grass", shore_width=14.0, deep_colour=(0.10, 0.22, 0.26), depth=0.55),
    "stone_pool": Water("stone_pool", 160.0, 112.0, (0.36, 0.55, 0.60), 0.88, "rect", 0.30, 0.40, True, True, "",
                        seed=5, shore="stone", shore_width=12.0, deep_colour=(0.12, 0.28, 0.36), depth=0.92),
}
PRESET_NAMES = {"puddle": "Simple puddle", "pond": "Simple pond", "muddy_puddle": "Muddy puddle",
                "natural_pond": "Natural pond", "stone_pool": "Stone pool"}


def _hex(value: Any, where: str) -> tuple[float, float, float]:
    text = str(value).strip().lstrip("#")
    if len(text) != 6 or any(c not in "0123456789abcdefABCDEF" for c in text):
        raise WaterError(f"{where} must be a colour like \"#3a6f8f\" (got {value!r})")
    return (int(text[0:2], 16) / 255.0, int(text[2:4], 16) / 255.0, int(text[4:6], 16) / 255.0)


def colour_hex(colour: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{round(c * 255):02x}" for c in colour)


def _number(value: Any, where: str, lo: float, hi: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lo <= value <= hi:
        raise WaterError(f"{where} must be a number from {lo:g} to {hi:g} (got {value!r})")
    return float(value)


# What a setting holds to mean "the preset's" (the behaviour's declared defaults: what adding it plainly writes).
UNSET = {"width": 0, "height": 0, "colour": "", "opacity": 0, "shape": "", "waves": -1, "reflection": -1, "rotation": 0,
         "seed": 0, "shore": "", "shore_width": -1, "deep_colour": "", "depth": -1, "ripples": -1, "passable": "",
         "wade_depth": -1}


def blocks(water: Water) -> bool:
    """Whether characters can't go into this water: passable "block", or "auto" and not ``walkable`` (as before)."""
    return water.passable == "block" or (water.passable == "auto" and not water.walkable)


def parse_water(raw: Any) -> Water:
    """A ``WaterSurface`` config checked and completed from its preset (a setting holding its ``UNSET`` value, or
    absent, is the preset's; ``target_tags`` is the behaviour's own)."""
    if not isinstance(raw, dict):
        raise WaterError("water settings must be an object like {\"preset\": \"pond\"}")
    raw = {k: v for k, v in raw.items()
           if k != "target_tags" and not (k in UNSET and not isinstance(v, bool) and v == UNSET[k])}
    unknown = set(raw) - _KEYS
    if unknown:
        raise WaterError(f"water: unknown setting(s) {', '.join(sorted(unknown))}")
    base = PRESETS.get(str(raw.get("preset", "puddle")))
    if base is None:
        raise WaterError(f"water preset must be one of {', '.join(PRESETS)} (got {raw.get('preset')!r})")
    shape = raw.get("shape", base.shape)
    if shape not in SHAPES:
        raise WaterError(f"water shape must be one of {', '.join(SHAPES)} (got {shape!r})")
    for key in ("rain_ripples", "walkable"):
        if key in raw and not isinstance(raw[key], bool):
            raise WaterError(f"water {key} must be true or false")
    sound = raw.get("step_sound", "")
    if not isinstance(sound, str):
        raise WaterError("water step_sound must be a sound file's path (or empty)")
    if base.preset in CLASSIC:
        given = sorted(k for k in LOOK_19B if k in raw)
        if given:
            raise WaterError(f"the simple {base.preset} has no {', '.join(given)} (a muddy_puddle, natural_pond or "
                             "stone_pool has)")
    shore = raw.get("shore", base.shore)
    if shore not in SHORES:
        raise WaterError(f"water shore must be one of {', '.join(SHORES)} (got {shore!r})")
    seed = raw.get("seed", base.seed)
    if isinstance(seed, bool) or not isinstance(seed, int) or not 1 <= seed <= 9999:
        raise WaterError(f"water seed must be a whole number from 1 to 9999 (got {seed!r})")
    passable = raw.get("passable", "auto")
    if passable not in PASSABLE:
        raise WaterError(f"water passable must be one of {', '.join(PASSABLE)} (got {passable!r})")
    return replace(
        base, width=_number(raw.get("width", base.width), "water width", 8, 8192),
        height=_number(raw.get("height", base.height), "water height", 8, 8192),
        colour=_hex(raw["colour"], "water colour") if "colour" in raw else base.colour,
        opacity=_number(raw.get("opacity", base.opacity), "water opacity", 0.05, 1.0), shape=shape,
        waves=_number(raw.get("waves", base.waves), "water waves", 0.0, 1.0),
        reflection=_number(raw.get("reflection", base.reflection), "water reflection", 0.0, 1.0),
        rain_ripples=bool(raw.get("rain_ripples", base.rain_ripples)), walkable=bool(raw.get("walkable", base.walkable)),
        step_sound=sound.strip(), rotation=_number(raw.get("rotation", base.rotation), "water rotation", -360, 360),
        seed=seed, shore=shore, shore_width=_number(raw.get("shore_width", base.shore_width), "water shore_width", 0, 64),
        deep_colour=_hex(raw["deep_colour"], "water deep_colour") if "deep_colour" in raw else base.deep_colour,
        depth=_number(raw.get("depth", base.depth), "water depth", 0.0, 1.0),
        ripples=_number(raw.get("ripples", base.ripples), "water ripples", 0.0, 1.0), passable=passable,
        wade_depth=_number(raw.get("wade_depth", WADE_DEPTH_DEFAULT), "water wade_depth", *WADE_DEPTH_M))


def outline(water: Water) -> tuple[float, tuple[float, ...], tuple[float, ...]]:
    """A natural shape's edge, as its radius (1: the ellipse its size makes) about its centre at angle a:
    ``c0 + sum(amp[k] * cos((k + 2) a + phase[k]))``, scaled to fit inside that ellipse. The seed picks it; the shader
    draws it from the same numbers, so what is walked through is what is seen."""
    if water.shape != "natural":
        return 1.0, (0.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 0.0)
    return _harmonics(water.seed)


@functools.lru_cache(maxsize=256)
def _harmonics(seed: int) -> tuple[float, tuple[float, ...], tuple[float, ...]]:
    """A natural outline's numbers for ``seed`` (worked out once: every frame lays out its room's water)."""
    rng = random.Random(seed * 7919 + 13)
    amp = [rng.uniform(0.55, 1.0) * a for a in (0.10, 0.075, 0.05, 0.035)]
    phase = [rng.uniform(0.0, math.tau) for _ in amp]
    top = max(1.0 + sum(a * math.cos((k + 2) * th + p) for k, (a, p) in enumerate(zip(amp, phase)))
              for th in (i * math.tau / 360 for i in range(360)))
    return 1.0 / top, tuple(a / top for a in amp), tuple(phase)


def _radius(c0: float, amp: tuple[float, ...], phase: tuple[float, ...], th: float) -> float:
    return c0 + sum(a * math.cos((k + 2) * th + p) for k, (a, p) in enumerate(zip(amp, phase)))


def _local(water: Water, centre: tuple[float, float], point: tuple[float, float]) -> tuple[float, float]:
    """``point`` (px) in the water's own frame: about its centre, its rotation undone."""
    a = math.radians(water.rotation)
    dx, dy = point[0] - centre[0], point[1] - centre[1]
    return dx * math.cos(a) + dy * math.sin(a), -dx * math.sin(a) + dy * math.cos(a)


def outline_points(water: Water, centre: tuple[float, float], n: int = 48) -> list[tuple[float, float]]:
    """The water's edge (px), for Studio's outline."""
    a = math.radians(water.rotation)
    c0, amp, phase = outline(water)
    out = []
    for i in range(n):
        th = i * math.tau / n
        if water.shape == "rect":
            k = max(abs(math.cos(th)), abs(math.sin(th)))
            lx, ly = math.cos(th) / k, math.sin(th) / k
        else:
            r = _radius(c0, amp, phase, th)
            lx, ly = r * math.cos(th), r * math.sin(th)
        lx, ly = lx * water.width / 2, ly * water.height / 2
        out.append((centre[0] + lx * math.cos(a) - ly * math.sin(a), centre[1] + lx * math.sin(a) + ly * math.cos(a)))
    return out


def extent(water: Water) -> tuple[float, float]:
    """The width and height (px) of the box round the water's outline as turned (a blocking pond's collider)."""
    if water.shape == "rect":
        a = math.radians(water.rotation)
        c, s = abs(math.cos(a)), abs(math.sin(a))
        return round(water.width * c + water.height * s, 2), round(water.width * s + water.height * c, 2)
    edge = outline_points(water, (0.0, 0.0), 360)
    return (round(2 * max(abs(x) for x, _y in edge), 2), round(2 * max(abs(y) for _x, y in edge), 2))


def inside(water: Water, centre: tuple[float, float], point: tuple[float, float], margin: float = 0.0) -> bool:
    """Whether ``point`` (px) is on the water's surface (``margin`` px in from its edge)."""
    hw, hh = water.width / 2 - margin, water.height / 2 - margin
    if hw <= 0 or hh <= 0:
        return False
    lx, ly = _local(water, centre, point)
    dx, dy = lx / hw, ly / hh
    if water.shape == "rect":
        return abs(dx) <= 1.0 and abs(dy) <= 1.0
    r = _radius(*outline(water), math.atan2(dy, dx))
    return dx * dx + dy * dy <= r * r


def inset(water: Water, centre: tuple[float, float], point: tuple[float, float]) -> float:
    """About how far (px) ``point`` lies in from the water's edge (negative outside): along the line from its centre
    for a round or natural outline, to the nearer side for a rectangle. It grows steadily inwards (R4B: blocking
    water is more over its limit the further in, so one put in it can only walk out)."""
    hw, hh = water.width / 2, water.height / 2
    lx, ly = _local(water, centre, point)
    if water.shape == "rect":
        return min(hw - abs(lx), hh - abs(ly))
    dx, dy = lx / hw, ly / hh
    th = math.atan2(dy, dx)
    r = _radius(*outline(water), th)
    edge = r * math.hypot(math.cos(th) * hw, math.sin(th) * hh)  # its centre to its edge, this way (px)
    return edge * (1.0 - math.hypot(dx, dy) / max(r, 1e-9))


# --- a room's water: registry, clock, footsteps (window attributes; reset on every room load) ----------------------

@dataclass
class Body:
    """A water surface in the room as its behaviour sees it: its object (for where it is) and its settings."""
    entity: Any
    water: Water

    def place(self) -> tuple[float, float, float]:
        """Its centre (m) and its water level (m)."""
        e = self.entity
        level = (getattr(e, "mesh_entity_data", None) or {}).get("elevation", 0.0)
        level = float(level) if isinstance(level, (int, float)) and not isinstance(level, bool) else 0.0
        return (float(e.center_x) / PX_PER_M, float(e.center_y) / PX_PER_M, level / PX_PER_M)


def reset(window: Any) -> None:
    """A room is loading: its water surfaces register as their behaviours start."""
    window.water_bodies = []
    window.water_steps = []
    window.water_time = 0.0
    window.scene_water_error = None
    layer = getattr(window, "scene_water", None)
    if layer is not None:
        layer.release()
    window.scene_water = None


def advance(window: Any, delta_time: float) -> None:
    """The water's clock: it runs while the room has water, puddles and ponds or (HD-2D) rivers."""
    renderer = getattr(window, "hd2d_renderer", None)
    if getattr(window, "water_bodies", None) or (renderer is not None and renderer.settings.rivers):
        window.water_time = float(getattr(window, "water_time", 0.0)) + max(0.0, float(delta_time))


def add_step(window: Any, x_m: float, y_m: float) -> None:
    """A footstep in water at (x, y) m: its ripple starts now."""
    steps = getattr(window, "water_steps", None)
    if steps is None:
        steps = window.water_steps = []
    steps.append((x_m, y_m, float(getattr(window, "water_time", 0.0))))
    del steps[:-MAX_STEPS]


def rain_rate(effects: Any, enabled: Any) -> float:
    """How hard the room's rain falls, for ripples: 1.0 is the rain preset's default 3,000 drops (capped at 2)."""
    rate = 0.0
    for effect, on in zip(effects or (), enabled or ()):
        if on and effect.preset == "rain":
            rate += effect.count / 3000.0 * max(0.25, effect.speed)
    return min(2.0, rate)


VS = """
#version 330
uniform mat4 u_vp; uniform int u_flat;
in vec2 in_corner; in vec4 in_rect; in vec4 in_info; in vec4 in_colour; in vec4 in_look;
in vec4 in_deep; in vec4 in_shore; in vec4 in_amp; in vec4 in_phase;
out vec3 v_world; flat out vec4 v_rect; flat out vec4 v_info; flat out vec4 v_colour; flat out vec4 v_look;
flat out vec4 v_deep; flat out vec4 v_shore; flat out vec4 v_amp; flat out vec4 v_phase; flat out int v_index;
void main() {
    v_index = gl_InstanceID;  // (R4: rivers flowing into it name it so)
    // in_rect: centre x, y (m), half width, half height (m); in_info: level z (m), shape (0 ellipse, 1 rect,
    // 2 natural), kind (0 puddle, 1 pond: Stage 19A's look; 2 Stage 19B's material), rain ripples (0/1); in_look:
    // waves, reflection, seed, ripple strength; in_deep: deep colour, depth; in_shore: shore (0 none, 1 mud, 2 grass,
    // 3 stone), its width (m), rotation (rad), the natural outline's c0; in_amp, in_phase: its harmonics (outline())
    float a = in_shore.z;
    vec2 off = in_corner * (in_rect.zw + in_shore.y + (in_shore.x > 2.5 ? 0.16 : 0.0));  // the bank round it too
    off = vec2(cos(a) * off.x - sin(a) * off.y, sin(a) * off.x + cos(a) * off.y);
    vec3 world = vec3(in_rect.xy + off, in_info.x);
    v_world = world; v_rect = in_rect; v_info = in_info; v_colour = in_colour; v_look = in_look;
    v_deep = in_deep; v_shore = in_shore; v_amp = in_amp; v_phase = in_phase;
    gl_Position = u_flat == 1 ? u_vp * vec4(world.x * 32.0, (world.y + world.z) * 32.0, 0.0, 1.0)
                              : u_vp * vec4(world, 1.0);
}
"""
# What ponds and rivers share (#461): their uniforms (WaterLayer._uniforms sets them on either program), helpers, the
# rain's and footsteps' rings and the reflection march into the one copy of the frame
SHARED_GLSL = """
uniform float u_time; uniform int u_flat; uniform mat4 u_vp; uniform vec3 u_eye; uniform vec3 u_sky; uniform vec3 u_light;
uniform float u_rain; uniform int u_shelter; uniform sampler2D u_precip; uniform mat4 u_precip_vp;
uniform vec4 u_steps[8]; uniform int u_steps_n;
uniform int u_reflect; uniform sampler2D u_scene; uniform sampler2D u_scene_depth; uniform vec2 u_screen;
uniform int u_lit;  // 1: lit by the room's sun, lamps and shadows (HD-2D: engine.hd2d.lighting), else u_light
// Milestone 20A: the sculpted ground's heights (m) at its corners, for water whose shore is the ground ("terrain")
uniform int u_has_terrain; uniform sampler2D u_terrain; uniform vec4 u_terrain_box;  // origin x, y (m), cell (m), -
// R4 (#461): rivers flowing into ponds (engine.hd2d.river.Mouth), MAX_MOUTHS of them. Where each crosses its pond's
// shore: x, y (m), the tangent downstream; its half width there (m), how far along the river (m), which pond (its
// place in the ponds' instances), the pond's level (m, as drawn). For the river's side, the pond's outline and look:
// centre x, y and half size (m); shape, rotation (rad), the outline's c0, its waves' strength; its harmonics; its
// shallow colour and opacity, deep colour and depth; waves, reflection, seed, ripple strength
const int MAX_MOUTHS = """ + str(MAX_MOUTHS) + """;
uniform int u_mouths_n;
uniform vec4 u_mouth_at[MAX_MOUTHS]; uniform vec4 u_mouth_info[MAX_MOUTHS]; uniform vec4 u_mouth_rect[MAX_MOUTHS];
uniform vec4 u_mouth_shape[MAX_MOUTHS]; uniform vec4 u_mouth_amp[MAX_MOUTHS]; uniform vec4 u_mouth_phase[MAX_MOUTHS];
uniform vec4 u_mouth_colour[MAX_MOUTHS]; uniform vec4 u_mouth_deep[MAX_MOUTHS]; uniform vec4 u_mouth_look[MAX_MOUTHS];
// 1 if its shore is the sculpted ground (how deep it looks: its real depth), else 0; 1 if the room's rain rings it
uniform vec4 u_mouth_kind[MAX_MOUTHS];
const float MOUTH_BLEND = """ + repr(MOUTH_BLEND_M) + """;  // the river takes on the pond's look over this (m)
""" + OUTPUTS + LIGHTING_GLSL + """
float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
// rings on the surface: a ring of radius r (m) about c, as a narrow band, fading with age 0..1
float ring(vec2 q, vec2 c, float r, float age) {
    float d = abs(length(q - c) - r);
    return (1.0 - smoothstep(0.0, 0.045, d)) * (1.0 - age);
}
// the sculpted ground's height (m) at p: its corners' heights, read between them
float ground_at(vec2 p) {
    vec2 n = vec2(textureSize(u_terrain, 0));
    return texture(u_terrain, ((p - u_terrain_box.xy) / u_terrain_box.z + 0.5) / n).r;
}
vec3 shade(vec3 c) { return floor(c * 24.0 + 0.5) / 24.0; }  // a few flat shades: pixel art, not a gradient
// how far outside a pond's edge m is (m; negative: in from it), m in the pond's own frame, b its half size, shape
// (0 ellipse, 1 rect, 2 natural) and the natural outline's numbers (outline())
float outline_sd(vec2 m, vec2 b, float shape, float c0, vec4 amp, vec4 phase) {
    if (shape > 0.5 && shape < 1.5) {  // a rectangle, its corners rounded
        float rad = min(0.5, 0.3 * min(b.x, b.y));
        vec2 d = abs(m) - b + rad;
        return length(max(d, 0.0)) + min(max(d.x, d.y), 0.0) - rad;
    }
    // the ellipse or natural outline: f = rho - r(theta) in the size's frame, over its gradient in metres (so long,
    // narrow water keeps an even bank); inside, no further than the short half-axis allows
    vec2 l = m / b;
    float rho = length(l);
    vec4 k = vec4(2.0, 3.0, 4.0, 5.0);
    float th = atan(l.y, l.x), r = 1.0, dr = 0.0;
    if (shape > 1.5) {
        r = c0 + dot(amp, cos(k * th + phase));
        dr = -dot(amp * k, sin(k * th + phase));
    }
    if (rho < 1e-4) return -min(b.x, b.y) * r;
    float f = rho - r;
    // (the outline's turn, r'/rho, only matters near the edge: bounded, it doesn't swamp the middle)
    vec2 g = (l / rho - dr * vec2(-l.y, l.x) / (rho * max(rho, 0.5))) / b;
    float d = f / max(length(g), 1e-4);
    return f < 0.0 ? max(d, -min(b.x, b.y) * (r - rho)) : d;
}
const float LIFT = """ + repr(LIFT_M) + """;  // the surface stands this far above its level (LIFT_M)
// rain: in cells of 0.5 m each starts rings at hashed places and moments, as often as the rain is heavy; none where
// something above (a roof, the deck) keeps it off the water at q, height z
float rain_rings(vec2 q, float z, float t, float seed) {
    float rings = 0.0;
    bool rained = true;
    if (u_shelter == 1) {
        vec3 mp = (u_precip_vp * vec4(q, z + 0.05, 1.0)).xyz * 0.5 + 0.5;
        if (mp.x >= 0.0 && mp.x <= 1.0 && mp.y >= 0.0 && mp.y <= 1.0 && texture(u_precip, mp.xy).r < mp.z - 0.002) rained = false;
    }
    if (rained) {
        vec2 cell0 = floor(q / 0.5);
        for (int i = -1; i <= 1; i++) for (int j = -1; j <= 1; j++) {
            vec2 cell = cell0 + vec2(i, j);
            for (int k = 0; k < 2; k++) {
                float h = hash(cell * 1.31 + float(k) * 7.7 + seed);
                float period = 1.6 / max(u_rain, 0.05);  // a cell's ring comes round this often (s)
                float phase = t / period + h;
                float age = fract(phase);
                vec2 c = (cell + vec2(hash(cell + floor(phase) * 3.1 + float(k)), hash(cell * 2.7 + floor(phase) * 5.3 + float(k)))) * 0.5;
                if (age < 0.6) rings += ring(q, c, age / 0.6 * 0.28, age / 0.6);
            }
        }
    }
    return rings;
}
// footsteps: a ring from each (added to rings), and a few splash pixels at first (added to splash)
void step_rings(vec2 q, float t, inout float rings, inout float splash) {
    for (int i = 0; i < u_steps_n; i++) {
        float age = (t - u_steps[i].z) / 1.0;
        if (age < 0.0 || age > 1.0) continue;
        rings += 1.4 * ring(q, u_steps[i].xy, 0.06 + age * 0.55, age);
        vec2 off = q - u_steps[i].xy;
        if (age < 0.25 && length(off) < 0.12 + age * 0.4 && hash(floor(q * 32.0) + floor(t * 12.0)) > 0.86) splash += 1.0;
    }
}
// what the surface at p mirrors along r: what's on screen there (the copy of the frame), else the sky; ``fade``:
// what stands far away fades to the sky (Stage 19B's material)
vec3 mirror(vec3 p0, vec3 r, bool fade) {
    vec3 refl = u_sky;
    for (int s = 1; s <= 10; s++) {
        vec3 p = p0 + r * (0.18 * float(s * s) * 0.5);
        vec4 c = u_vp * vec4(p, 1.0);
        vec3 ndc = c.xyz / c.w;
        vec2 uv = ndc.xy * 0.5 + 0.5;
        if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) break;
        float scene_d = texture(u_scene_depth, uv).r;
        // something on screen in front of the ray here, standing above the water (the ground beside it, met at a
        // grazing angle, would mirror as dark blotches)
        if (scene_d < ndc.z * 0.5 + 0.5 - 0.000002 && p.z - p0.z > 0.3) {
            // towards the picture's edges it gives way to the sky (what's off screen can't be mirrored)
            float edge = smoothstep(0.0, 0.14, min(min(uv.x, 1.0 - uv.x), min(uv.y, 1.0 - uv.y)));
            // Stage 19B: what stands near the water is mirrored, what's far away fades to the sky (a few far
            // hits read as noise, not a reflection)
            float near = fade ? 1.0 - smoothstep(1.2, 3.5, 0.09 * float(s * s)) : 1.0;
            refl = mix(u_sky, texture(u_scene, (floor(uv * u_screen) + 0.5) / u_screen).rgb, edge * near);
            break;
        }
    }
    return refl;
}
"""
FS = """
#version 330
in vec3 v_world; flat in vec4 v_rect; flat in vec4 v_info; flat in vec4 v_colour; flat in vec4 v_look;
flat in vec4 v_deep; flat in vec4 v_shore; flat in vec4 v_amp; flat in vec4 v_phase; flat in int v_index;
""" + SHARED_GLSL + """
// a point (m) in the water's own frame: about its centre, its rotation undone
vec2 to_local(vec2 p) {
    vec2 d = p - v_rect.xy;
    float a = v_shore.z;
    return vec2(cos(a) * d.x + sin(a) * d.y, -sin(a) * d.x + cos(a) * d.y);
}
// the edge's radius in the direction of l (1: the ellipse the size makes; a natural shape's harmonics: outline())
float radius_at(vec2 l) {
    if (v_info.y < 1.5) return 1.0;
    float th = atan(l.y, l.x);
    return v_shore.w + dot(v_amp, cos(vec4(2.0, 3.0, 4.0, 5.0) * th + v_phase));
}
// Stage 19A's measure: 1 at the middle, 0 at the edge
float inside_at(vec2 m) {
    vec2 l = m / v_rect.zw;
    if (v_info.y > 0.5 && v_info.y < 1.5) return 1.0 - max(abs(l.x), abs(l.y)) * 0.96 - 0.04 * length(l);
    return 1.0 - length(l) / radius_at(l);
}
// how far outside the edge (m; negative: in from it)
float sd_at(vec2 m) { return outline_sd(m, v_rect.zw, v_info.y, v_shore.w, v_amp, v_phase); }
// R4: where a river flows into this pond, how far in from that river's banks (m) a point is, fading over
// MOUTH_BLEND in from the shore (sd: how far outside it the point is; the river blends by the same distance), so its
// shore is open there: no bank, no edge drawn across the river; -1 elsewhere. reach: how far out its shore goes (its
// bank isn't drawn over the river's water, near where it enters only: not a small pond's far bank)
float mouth_open(vec2 q, float reach, float sd) {
    float open = -1.0;
    for (int i = 0; i < u_mouths_n; i++) {
        if (int(u_mouth_info[i].z + 0.5) != v_index) continue;
        vec2 d = q - u_mouth_at[i].xy, tng = u_mouth_at[i].zw;
        float along = dot(d, tng), across = abs(tng.x * d.y - tng.y * d.x), h = u_mouth_info[i].x;
        // (from a half width upstream of where its middle crosses: the shore may cross it at a slant)
        float ahead = sd >= 0.0 ? h + reach + 0.4 : MOUTH_BLEND + 2.0 * h;
        if (across < h && along > -(reach + 0.4 + h) && along < ahead)
            open = max(open, (h - across) * (1.0 - smoothstep(0.0, MOUTH_BLEND, max(-sd, 0.0))));
    }
    return open;
}
// a stone rim: cells of about 0.26 m, a stone in each whose centre lies on the bank (or just over the water's edge),
// drawn whole with its mortar round it and lit on its sunward side; (rgb, 1) where one is, else 0
vec4 stone(vec2 q, float reach, vec2 sun) {
    vec2 g = q / 0.26, gi = floor(g);
    float d1 = 9.0, d2 = 9.0;
    vec2 best = vec2(0.0), centre = vec2(0.0);
    for (int i = -1; i <= 1; i++) for (int j = -1; j <= 1; j++) {
        vec2 cell = gi + vec2(i, j);
        vec2 c = cell + 0.15 + 0.7 * vec2(hash(cell + v_look.z), hash(cell * 1.7 + 4.1 + v_look.z));
        float d = length(g - c);
        if (d < d1) { d2 = d1; d1 = d; best = cell; centre = c; } else if (d < d2) d2 = d;
    }
    float at = sd_at(to_local(centre * 0.26));
    if (at < -0.05 || at > reach - 0.05) return vec4(0.0);
    if (d2 - d1 < 0.14) return vec4(0.21, 0.20, 0.19, 1.0);  // mortar
    float h = hash(best * 2.3 + 1.9);
    vec3 c = vec3(0.52, 0.51, 0.48) * (0.80 + 0.30 * h) + vec3(0.03, 0.01, -0.02) * (h - 0.5);
    vec2 o = g - centre;
    float towards = dot(normalize(o + 1e-4), normalize(sun + 1e-4));
    if (length(o) > 0.2) c *= towards > 0.3 ? 1.16 : (towards < -0.3 ? 0.80 : 1.0);
    return vec4(c, 1.0);
}
// the bank outside the edge (b: 0 at the water .. 1 at its outer reach), per texel so its edge is ragged pixel art
vec4 bank(vec2 q, float b, int shore) {
    float n = hash(floor(q * 32.0) * 0.37 + v_look.z);
    float fade = 1.0 - b + (n - 0.5) * 0.45;
    float ragged = 1.0 - b + (n - 0.5) * 0.25;
    if (shore == 1) {  // mud: wet ground (whatever it is: path or grass) darkest at the water, a pebble here and there
        if (hash(floor(q * 8.0) + 3.1) > 0.93 && n > 0.6 && b > 0.2) return vec4(0.46, 0.42, 0.36, 0.9);
        return ragged > 0.62 ? vec4(0.20, 0.15, 0.10, 0.5) : (ragged > 0.3 ? vec4(0.20, 0.15, 0.10, 0.3) : vec4(0.0));
    }
    if (shore == 2) {  // grass: an earth lip at the water, then reeds in clumps on damp grass
        if (b < 0.2 + (n - 0.5) * 0.12) return vec4(0.28, 0.21, 0.13, 0.9);
        vec2 cell = floor(q / 0.25), tx = floor(q * 32.0) - cell * 8.0;  // 8 x 8 texels a cell
        float h = hash(cell + 7.3 + v_look.z);
        if (h > 0.62 && b < 0.85) {  // a clump: two or three blades, rising from its foot (seen upright: the camera
            for (int k = 0; k < 3; k++) {  // looks along the ground, so a stroke north on it stands up on screen)
                float col = 1.0 + float(k) * 2.0 + floor(hash(cell + float(k)) * 2.0);
                float tall = 3.0 + floor(hash(cell * 1.3 + float(k)) * 4.0);
                if (tx.x == col && tx.y >= 1.0 && tx.y < 1.0 + tall && (k < 2 || h > 0.8))
                    return vec4(mix(vec3(0.13, 0.27, 0.08), vec3(0.47, 0.50, 0.21), (tx.y - 1.0) / tall), 1.0);
            }
        }
        return ragged > 0.55 ? vec4(0.10, 0.20, 0.06, 0.28) : vec4(0.0);
    }
    return vec4(0.0);  // stone: its stones only (stone())
}
const float STONE_OVER = 0.16;  // an outer stone may reach this far past its bank's width (drawn whole)
void main() {
    // the pixel grid: everything is worked out at the centre of this fragment's texel (32 per metre)
    vec2 q = (floor(v_world.xy * 32.0) + 0.5) / 32.0;
    vec2 m = to_local(q);
    vec2 local = m / v_rect.zw;  // -1..1 across the surface (the water's own frame)
    float shape = v_info.y, kind = v_info.z;
    bool material = kind > 1.5;  // Stage 19B: a bank, shallows and depths; else Stage 19A's look, exactly
    vec3 view = u_flat == 1 ? vec3(0.0, 0.35, -0.94) : normalize(vec3(q, v_world.z) - u_eye);
    vec3 light = u_lit == 1 ? light_at(vec3(q, v_world.z), vec3(0.0, 0.0, 1.0), false) : u_light;
    vec2 sun = u_lit == 1 ? u_sun_dir.xy : vec2(-0.45, -0.55);
    int shore = int(v_shore.x + 0.5);
    float reach = v_shore.y, inside = 0.0, edge_m = 0.0, shadow = 1.0, water_depth = -1.0;
    float open = -1.0;  // R4: a river's mouth (its water here: mouth_open)
    if (material) {
        float sd = sd_at(m);
        if (sd > reach + (shore == 3 ? STONE_OVER : 0.0) || (sd > 0.0 && (shore == 0 || shore == 4))) discard;
        if (u_mouths_n > 0) open = mouth_open(q, reach + STONE_OVER, sd);
        if (open >= 0.0 && sd >= 0.0) discard;  // the river's water, not this pond's bank
        if (shore == 4 && u_has_terrain == 1) {  // the sculpted ground is the shore: water only where it lies above it
            water_depth = v_world.z - LIFT - ground_at(q);
            if (water_depth <= 0.0) discard;
        }
        if (shore == 3 && sd > -0.4 && open < 0.0) {  // (deeper in, no stone reaches)
            vec4 s = stone(q, reach, sun);
            if (s.a > 0.0) { f_color = vec4(shade(s.rgb * light), 1.0); f_emit = vec4(0.0, 0.0, 0.0, 1.0); return; }
        }
        if (sd >= 0.0) {
            if (sd > reach) discard;  // (past the stones)
            vec4 c = bank(q, sd / max(reach, 1e-3), shore);
            if (c.a <= 0.0) discard;
            f_color = vec4(shade(c.rgb * light), c.a);
            f_emit = vec4(0.0, 0.0, 0.0, c.a);
            return;
        }
        // the water lies a little below the ground, so near its far edge the view ray meets the bank's side before
        // it reaches the water: that side is seen there (and its shadow on the water just short of it)
        float drop = open >= 0.0 ? 0.0 : (shore == 1 ? 0.03 : (shore == 2 ? 0.09 : (shore == 3 ? 0.14 : 0.0)));
        vec2 down = view.xy * (drop / max(0.2, -view.z));
        if (drop > 0.0 && sd_at(to_local(q + down)) > 0.0) {
            float lo = 0.0, hi = 1.0;  // where along the way down the ray meets the side: how far below the ground
            for (int i = 0; i < 5; i++) {
                float mid = 0.5 * (lo + hi);
                if (sd_at(to_local(q + down * mid)) > 0.0) hi = mid; else lo = mid;
            }
            float below = hi * drop;
            vec3 side = light_at(vec3(q, v_world.z - below), vec3(-normalize(view.xy + 1e-4), 0.0), false);
            side = u_lit == 1 ? side : u_light * 0.8;
            vec3 c;
            if (shore == 3) {  // stone courses
                float row = floor(below / 0.07);
                float along = floor((q.x + q.y) / 0.18 + row * 0.5);
                c = fract(below / 0.07) < 0.22 ? vec3(0.20, 0.19, 0.18)
                                               : vec3(0.46, 0.45, 0.42) * (0.82 + 0.25 * hash(vec2(along, row)));
            } else {  // earth, darker and wetter towards the water
                c = mix(vec3(0.33, 0.24, 0.15), vec3(0.20, 0.15, 0.10), hi) * (0.9 + 0.2 * hash(floor(q * 32.0)));
            }
            f_color = vec4(shade(c * side), 1.0);
            f_emit = vec4(0.0, 0.0, 0.0, 1.0);
            return;
        }
        if (drop > 0.0 && sd_at(to_local(q + down * 1.8)) > 0.0) shadow = 0.7;
        // (at a river's mouth: from the river's banks, as the river measures it; met smoothly, no corner)
        float kink = max(0.3 - abs(open + sd), 0.0) / 0.3;
        edge_m = open >= 0.0 ? max(-sd, open) + kink * kink * 0.075 : -sd;
    } else {
        inside = inside_at(m);
        if (inside < 0.0) discard;  // (rivers flow only into the newer looks: no mouth here)
        edge_m = inside * min(v_rect.z, v_rect.w);  // roughly how far in from the edge (m)
    }
    float t = u_time, seed = v_look.z;
    // gentle waves: their slope bends the surface's normal
    float w = v_look.x * (material ? 0.045 : (kind > 0.5 ? 0.06 : 0.025));
    vec2 slope = w * vec2(cos(q.x * 5.1 + q.y * 1.7 + t * 1.3 + seed) * 5.1 + cos(q.x * -2.3 + q.y * 4.6 + t * 0.9) * -2.3,
                          cos(q.x * 5.1 + q.y * 1.7 + t * 1.3 + seed) * 1.7 + cos(q.x * -2.3 + q.y * 4.6 + t * 0.9) * 4.6);
    float splash = 0.0;
    float rings = u_rain > 0.0 && v_info.w > 0.5 ? rain_rings(q, v_world.z, t, seed) : 0.0;
    step_rings(q, t, rings, splash);
    rings *= v_look.w;
    vec3 n = normalize(vec3(-slope + rings * 0.35 * normalize(local + 0.001), 1.0));
    // the water's own colour. Stage 19A: a pond darker towards its middle, lighter at its rim. Stage 19B: from its
    // shallow colour at the edge (where the ground beneath shows through) to its deep colour, as soon as its depth says
    vec3 col = v_colour.rgb;
    float deep = 0.0, rim = 0.0, alpha_water = v_colour.a;
    if (material) {
        // how deep it looks: from its edge inwards, or (its shore the ground) from how deep the water really is
        deep = water_depth >= 0.0 ? smoothstep(0.0, 0.05 + 1.2 * (1.0 - v_deep.w), water_depth)
                                  : smoothstep(0.02, 0.1 + 1.5 * (1.0 - v_deep.w), edge_m);
        col = mix(col, v_deep.rgb, deep);
        alpha_water = v_colour.a * mix(0.45, 1.0, deep);
    } else {
        deep = kind > 0.5 ? smoothstep(0.1, 1.6, edge_m) : 0.0;
        col *= mix(1.0, 0.62, deep);
        rim = (kind > 0.5 ? 1.0 - smoothstep(0.0, 0.16, edge_m) : 1.0 - smoothstep(0.0, 0.06, edge_m));
    }
    // what it mirrors: the sky, or (HD-2D) what's on screen along the mirrored view ray
    // the mirror is calmer than the surface: a quarter of the waves' slope (the full slope scattered it to blotches)
    vec3 r = reflect(view, normalize(vec3(-slope * 0.25, 1.0)));
    vec3 refl = u_reflect == 1 ? mirror(vec3(q, v_world.z), r, material) : u_sky;
    float facing = clamp(-view.z, 0.0, 1.0);
    vec3 lit;
    if (material) {
        // Stage 19B: the mirror takes the water's own hue and stays under its colour (strongest where deep)
        vec3 hue = col / max(max(col.r, col.g), max(col.b, 0.05));
        refl = mix(refl, refl * hue, 0.35);
        float fresnel = v_look.y * mix(0.6, 0.15, facing) * mix(0.55, 1.0, deep);
        lit = mix(col * light, refl, fresnel) * shadow;
        // slow glints: short light dashes drifting over open water, as many as its waves
        float g = sin(q.y * 26.0 + t * 1.1 + sin(q.x * 2.7 + seed) * 2.5) * sin(q.x * 3.7 - t * 0.4 + q.y * 0.9);
        if (g > 0.95 && deep > 0.25) lit = mix(lit, vec3(0.78, 0.88, 0.92) * light, 0.35 * min(1.0, v_look.x * 2.5));
    } else {
        float fresnel = v_look.y * mix(0.85, 0.35, facing);
        lit = mix(col * light, refl, fresnel);
    }
    lit += vec3(0.85, 0.92, 1.0) * clamp(rings, 0.0, 1.0) * 0.35 * (material ? light : vec3(1.0));  // rings catch the light
    float alpha;
    if (material) {
        // the near edge's waterline catches the light (a texel wide, crisp: no soft rim all round)
        bool waterline = water_depth >= 0.0 ? water_depth < 0.025  // (all round, where it meets the ground)
                                            : edge_m < 0.045 && sd_at(to_local(q - normalize(view.xy + 1e-4) * 0.05)) > 0.0
                                              && open < 0.0;
        lit = mix(lit, vec3(0.80, 0.86, 0.86) * light, (waterline ? 0.45 : 0.0) + clamp(splash, 0.0, 1.0) * 0.8);
        alpha = clamp((waterline ? max(alpha_water, 0.85) : alpha_water) + clamp(rings, 0.0, 1.0) * 0.2 + splash * 0.6, 0.0, 1.0);
    } else {
        lit = mix(lit, vec3(0.88, 0.94, 1.0) * light, rim * 0.35 + clamp(splash, 0.0, 1.0) * 0.8);
        alpha = clamp(v_colour.a * smoothstep(0.0, 0.04, inside * 2.0) + clamp(rings, 0.0, 1.0) * 0.2 + splash * 0.6, 0.0, 1.0);
    }
    f_color = vec4(shade(lit), alpha);
    f_emit = vec4(0.0, 0.0, 0.0, alpha);  // (water dims what glows beneath it as it dims its colour)
}
"""

# Rivers (#461, engine.hd2d.river): one continuous ribbon each, its vertices carrying the flow's frame (the tangent
# downstream, u metres downstream, v -1 left bank .. 1 right bank). Its own look (no bank or stones drawn: R1's
# rivers lie in a bed sculpted for them, the ground their shore), with the pond's lighting, rain and reflection march
# (SHARED_GLSL) into the same copy of the frame. It draws the footstep rings in window.water_steps: ponds and
# puddles add them (engine.behaviours.water_surface), and so does wading in a river's shallows (engine.hd2d.world)
RIVER_VS = """
#version 330
uniform mat4 u_vp;
uniform vec4 u_mouth_info[""" + str(MAX_MOUTHS) + """];
const float MOUTH_BLEND = """ + repr(MOUTH_BLEND_M) + """;
in vec3 in_pos; in vec2 in_tangent; in vec4 in_flow; in vec4 in_colour; in vec4 in_deep; in vec4 in_look;
in vec4 in_ends;
out vec3 v_world; out vec2 v_tangent; out vec3 v_flow; flat out float v_speed;
flat out vec4 v_colour; flat out vec4 v_deep; flat out vec4 v_look; flat out vec4 v_ends;
void main() {
    // in_flow: u (m downstream), v (-1 left .. 1 right), half width (m), flow (m/s); in_look: waves, reflection,
    // seed, rain ripples (0/1); in_ends (R4): its round caps' radii at its source and last point (m; 0 square), its
    // length (m), the mouth it flows into (-1 none)
    vec3 pos = in_pos;
    int slot = int(floor(in_ends.w + 0.5));
    if (slot >= 0) {  // over its last stretch before the pond's shore, its surface eases to the pond's level
        vec4 info = u_mouth_info[slot];
        pos.z = mix(pos.z, info.w, smoothstep(info.y - MOUTH_BLEND, info.y, in_flow.x));
    }
    v_world = pos; v_tangent = in_tangent; v_flow = in_flow.xyz; v_speed = in_flow.w;
    v_colour = in_colour; v_deep = in_deep; v_look = in_look; v_ends = in_ends;
    gl_Position = u_vp * vec4(pos, 1.0);
}
"""
RIVER_FS = """
#version 330
in vec3 v_world; in vec2 v_tangent; in vec3 v_flow; flat in float v_speed;
flat in vec4 v_colour; flat in vec4 v_deep; flat in vec4 v_look; flat in vec4 v_ends;
""" + SHARED_GLSL + """
void main() {
    // the pixel grid: everything at the centre of this fragment's texel (32 per metre), in the river's own frame there
    vec2 q = (floor(v_world.xy * 32.0) + 0.5) / 32.0;
    vec2 down = normalize(v_tangent), left = vec2(-down.y, down.x);
    vec2 to_q = q - v_world.xy;
    float u = v_flow.x + dot(to_q, down);  // metres downstream
    float across = v_flow.y * v_flow.z - dot(to_q, left);  // metres right of the middle
    float half_w = v_flow.z, edge_m = max(0.0, half_w - abs(across)), water_depth = -1.0;
    // R4: a round end is a half circle (engine.hd2d.river.capped: the same as its RiverIndex and its carved bowl)
    float cap0 = v_ends.x, cap1 = v_ends.y, length_m = v_ends.z;
    if (cap0 > 0.0 && u < cap0 && length(vec2(cap0 - u, across)) > cap0) discard;
    if (cap1 > 0.0 && u > length_m - cap1 && length(vec2(u - (length_m - cap1), across)) > cap1) discard;
    // R4: flowing into a pond: none of it in the pond's water (the pond's is drawn there: one surface), and over its
    // last MOUTH_BLEND before the shore it takes on the pond's look (blend 0 .. 1 at the shore), its current eased
    int slot = int(floor(v_ends.w + 0.5));
    float blend = 0.0, near_mouth = 1.0e9;
    vec4 colour = v_colour, deep_look = v_deep, pond_look = v_look, pond_shape = vec4(0.0, 0.0, 0.0, 0.045);
    if (slot >= 0) {
        vec4 rect = u_mouth_rect[slot];
        pond_shape = u_mouth_shape[slot];
        vec2 d = q - rect.xy;
        float a = pond_shape.y;
        vec2 m = vec2(cos(a) * d.x + sin(a) * d.y, -sin(a) * d.x + cos(a) * d.y);
        float sd = outline_sd(m, rect.zw, pond_shape.x, pond_shape.z, u_mouth_amp[slot], u_mouth_phase[slot]);
        if (sd < 0.0) discard;
        // by how near the shore it is (its whole width at the shore, which may cross it at a slant), over its last
        // stretch only (not where it passed the pond upstream)
        near_mouth = u_mouth_info[slot].y - MOUTH_BLEND - 2.0 * u_mouth_info[slot].x;
        blend = (1.0 - smoothstep(0.0, MOUTH_BLEND, sd)) * smoothstep(near_mouth - 1.0, near_mouth, u);
        colour = mix(v_colour, u_mouth_colour[slot], blend);
        deep_look = mix(v_deep, u_mouth_deep[slot], blend);
        pond_look = u_mouth_look[slot];
    }
    if (u_has_terrain == 1) {  // the sculpted ground is the shore: water only where it lies above it
        water_depth = v_world.z - LIFT - ground_at(q);
        if (water_depth <= 0.0) discard;
    }
    float t = u_time, seed = v_look.z, drift = v_speed * t;  // drift: how far the water has moved (still: none)
    vec3 view = normalize(vec3(q, v_world.z) - u_eye);
    vec3 light = u_lit == 1 ? light_at(vec3(q, v_world.z), vec3(0.0, 0.0, 1.0), false) : u_light;
    // waves carried downstream: long along the flow, short across it; their slope (in the river's frame) bends the
    // surface's normal
    float w = v_look.x * 0.045 * (1.0 - blend), a = u - drift;
    vec2 s = w * vec2(cos(a * 4.3 + across * 1.1 + seed) * 4.3 + cos(a * 2.2 - across * 3.7) * 2.2,
                      cos(a * 4.3 + across * 1.1 + seed) * 1.1 - cos(a * 2.2 - across * 3.7) * 3.7);
    vec2 slope = down * s.x - left * s.y;
    if (blend > 0.0) {  // towards the pond: the pond's own still waves (as its shader makes them), the current gone
        float pw = pond_look.x * pond_shape.w * blend, ps = pond_look.z;
        slope += pw * vec2(cos(q.x * 5.1 + q.y * 1.7 + t * 1.3 + ps) * 5.1 + cos(q.x * -2.3 + q.y * 4.6 + t * 0.9) * -2.3,
                           cos(q.x * 5.1 + q.y * 1.7 + t * 1.3 + ps) * 1.7 + cos(q.x * -2.3 + q.y * 4.6 + t * 0.9) * 4.6);
    }
    float splash = 0.0;
    float rings = 0.0;
    if (u_rain > 0.0) {  // (towards the pond, the pond's own rain rings, if the rain rings it)
        if (blend < 1.0 && v_look.w > 0.5) rings = rain_rings(q, v_world.z, t, seed) * (1.0 - blend);
        if (blend > 0.0 && u_mouth_kind[slot].y > 0.5) rings += rain_rings(q, v_world.z, t, pond_look.z) * blend;
    }
    step_rings(q, t, rings, splash);
    rings *= mix(1.0, pond_look.w, blend);
    vec3 n = normalize(vec3(-slope + rings * 0.35 * left * sign(across + 1e-4), 1.0));
    // its colour: from its shallow colour at the banks (or where the bed is near) to its deep colour
    float by_edge = smoothstep(0.02, 0.1 + 1.5 * (1.0 - deep_look.w), edge_m);
    float deep = water_depth >= 0.0 ? smoothstep(0.0, 0.05 + 1.2 * (1.0 - deep_look.w), water_depth) : by_edge;
    if (slot >= 0 && u_mouth_kind[slot].x < 0.5) deep = mix(deep, by_edge, blend);  // (as such a pond measures it)
    vec3 col = mix(colour.rgb, deep_look.rgb, deep);
    float alpha_water = colour.a * mix(0.45, 1.0, deep);
    vec3 r = reflect(view, normalize(vec3(-slope * 0.25, 1.0)));
    vec3 refl = u_reflect == 1 ? mirror(vec3(q, v_world.z), r, true) : u_sky;
    vec3 hue = col / max(max(col.r, col.g), max(col.b, 0.05));
    refl = mix(refl, refl * hue, 0.35);
    float facing = clamp(-view.z, 0.0, 1.0);
    float reflection = mix(v_look.y, pond_look.y, blend);
    vec3 lit = mix(col * light, refl, reflection * mix(0.6, 0.15, facing) * mix(0.55, 1.0, deep));
    // the current: short light streaks in lanes along the flow, drifting downstream (fastest mid-stream); still
    // water keeps them where they are
    float lane = floor(across / 0.125);  // lanes 4 texels wide
    float h = hash(vec2(lane, seed));
    float pace = mix(0.6, 1.0, 1.0 - pow(clamp(abs(across) / max(half_w, 1e-3), 0.0, 1.0), 2.0));
    float dash = fract((u - drift * pace * (0.85 + 0.3 * h)) / (1.2 + 1.6 * h) + h);
    if (h > 0.5 && dash < 0.2 && deep > 0.25)
        lit = mix(lit, vec3(0.80, 0.90, 0.93) * light, 0.25 * min(1.0, v_look.x * 2.0) * (1.0 - blend));
    if (blend > 0.0) {  // the pond's slow glints, as its shader draws them
        float g = sin(q.y * 26.0 + t * 1.1 + sin(q.x * 2.7 + pond_look.z) * 2.5) * sin(q.x * 3.7 - t * 0.4 + q.y * 0.9);
        if (g > 0.95 && deep > 0.25) lit = mix(lit, vec3(0.78, 0.88, 0.92) * light, 0.35 * min(1.0, pond_look.x * 2.5) * blend);
    }
    lit += vec3(0.85, 0.92, 1.0) * clamp(rings, 0.0, 1.0) * 0.35 * light;  // rings catch the light
    // the waterline where it meets its bed (a texel wide, crisp)
    // (not over its last stretch into a pond: its bed eases to the pond's depth there, its shallow banks no waterline,
    // as the pond draws none across its opening)
    bool waterline = (water_depth >= 0.0 ? water_depth < 0.025 : edge_m < 0.045) && u < near_mouth;
    lit = mix(lit, vec3(0.80, 0.86, 0.86) * light, (waterline ? 0.45 : 0.0) + clamp(splash, 0.0, 1.0) * 0.8);
    float alpha = clamp((waterline ? max(alpha_water, 0.85) : alpha_water) + clamp(rings, 0.0, 1.0) * 0.2 + splash * 0.6, 0.0, 1.0);
    f_color = vec4(shade(lit), alpha);
    f_emit = vec4(0.0, 0.0, 0.0, alpha);  // (water dims what glows beneath it as it dims its colour)
}
"""


class WaterLayer:
    """A room's water surfaces on the GPU: one program, one quad, one instance buffer (rewritten when the bodies
    change), and (HD-2D) a copy of the frame for reflections; ``release`` frees them all."""

    def __init__(self, ctx: Any, *, gl: Any) -> None:
        self.ctx, self.gl = ctx, gl
        self.program: Any = None
        self.quad: Any = None
        self.instances: Any = None
        self.geometry: Any = None
        self.copy: tuple[Any, Any, Any] | None = None  # (framebuffer, colour, depth) the frame is copied into
        self.count = 0
        self.draw_calls = 0
        self.depth_test = True  # False only to show what the depth test hides (diagnostics)
        self.shelter = True  # False: rain rings it even under a roof (diagnostics: the negative control)
        self._key: Any = None
        self.terrain: Any = None  # the sculpted ground's heights as a texture (set_terrain), if the room has any
        self._terrain_key: Any = None
        self.river_program: Any = None  # the room's rivers (set_rivers; made when it has any)
        self.river_buffers: tuple[Any, Any] | None = None  # (vertices, indices)
        self.river_geometry: Any = None
        self.river_box: tuple[float, ...] | None = None  # min x, y, z, max x, y, z (m)
        self.river_count = 0  # indices drawn (the buffers may hold more: room to grow)
        self.river_allocations = 0  # river buffers made (diagnostics: a drag writes into them)
        self.rivers: Any = ()
        self._river_key: Any = None  # (rivers, ponds) their buffers were made for
        self._rows: list[tuple[float, ...]] = []  # each pond's instance row (set_bodies)
        self.ponds: tuple[Any, ...] = ()  # the ponds as rivers' mouths see them (engine.hd2d.river.Pond)
        self.mouths: list[Any] = []  # R4: the rivers flowing into ponds, by slot (engine.hd2d.river.Mouth)
        self.mouth_problems: dict[str, str] = {}  # rivers with mouth "auto" that can't join a pond now, and why
        self._mouth_columns: dict[str, list[float]] = {}  # their uniforms (_columns), set on both programs each draw
        try:
            self.program = ctx.program(vertex_shader=VS, fragment_shader=FS)
            self.quad = ctx.buffer(data=array("f", [-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, 1.0, 1.0]).tobytes())
        except BaseException:
            self.release()
            raise

    def set_bodies(self, bodies: list[Body]) -> None:
        """The room's water surfaces now (cheap when nothing changed: their places and settings are compared)."""
        rows = []
        for i, body in enumerate(bodies):
            x, y, z = body.place()
            w = body.water
            c0, amp, phase = outline(w)
            classic = w.preset in CLASSIC
            rows.append((x, y, w.width / PX_PER_M / 2, w.height / PX_PER_M / 2,
                         z + LIFT_M, float(SHAPES.index(w.shape)), (1.0 if w.preset == "pond" else 0.0) if classic else 2.0,
                         1.0 if w.rain_ripples else 0.0, *w.colour, w.opacity, w.waves, w.reflection, 1.7 * i,
                         1.0 if classic else w.ripples, *w.deep_colour, w.depth,
                         float(SHORES.index(w.shore)), 0.0 if classic else w.shore_width / PX_PER_M,
                         math.radians(w.rotation), c0, *amp, *phase))
        key = tuple(rows)
        if key != self._key:  # (as rivers' mouths see them: the same numbers)
            from engine.hd2d.river import Pond, gated  # noqa: PLC0415

            self._rows = rows
            self.ponds = tuple(Pond(str(i), (row[0] * PX_PER_M, row[1] * PX_PER_M), (row[4] - LIFT_M) * PX_PER_M,
                                    body.water, gated(getattr(body.entity, "mesh_entity_data", None)))
                               for i, (row, body) in enumerate(zip(rows, bodies)))
        if key == self._key:
            return
        data = array("f", [v for row in rows for v in row]).tobytes() if rows else b""
        if self.geometry is not None and self.instances.size >= max(1, len(data)):
            if data:
                self.instances.write(data)
            self._key, self.count = key, len(rows)
            return
        self._free_geometry()
        self._key, self.count = None, 0  # recorded only once the geometry is made (a failure tries again)
        if not rows:
            self._key = key
            return
        self.instances = self.ctx.buffer(data=data)
        gl = self.gl
        self.geometry = self.ctx.geometry(
            [gl.BufferDescription(self.quad, "2f", ["in_corner"]),
             gl.BufferDescription(self.instances, "4f 4f 4f 4f 4f 4f 4f 4f",
                                  ["in_rect", "in_info", "in_colour", "in_look", "in_deep", "in_shore", "in_amp",
                                   "in_phase"], instanced=True)],
            mode=self.ctx.TRIANGLE_STRIP)
        self._key, self.count = key, len(rows)

    def set_rivers(self, rivers: tuple[Any, ...]) -> None:
        """The room's rivers (engine.hd2d.river.River, already checked): their ribbons made again only when they
        change (none: their buffers freed). A change that fits the buffers is written into them (Studio's River tool
        drags a point: no allocation a move while the river fits); one that doesn't gets new buffers with half as much
        again to spare."""
        if (rivers, self.ponds) == self._river_key:
            return
        from engine.hd2d import river as river_mod  # noqa: PLC0415

        if not rivers:
            self._free_rivers()
            return
        joined, problems = river_mod.mouths(rivers, self.ponds)  # R4: which flow into a pond (set_bodies' ponds)
        slots = {rid: (slot, mouth) for slot, (rid, mouth) in enumerate(joined.items())}
        data, idx = river_mod.vertices(rivers, LIFT_M, slots)
        vertices, indices = data.tobytes(), idx.tobytes()
        if self.river_program is None:
            self.river_program = self.ctx.program(vertex_shader=RIVER_VS, fragment_shader=RIVER_FS)
        buffers = self.river_buffers
        if buffers is None or buffers[0].size < len(vertices) or buffers[1].size < len(indices):
            self._free_rivers()
            vbo = self.ctx.buffer(reserve=len(vertices) * 3 // 2)
            ibo = self.ctx.buffer(reserve=len(indices) * 3 // 2)
            self.river_buffers = (vbo, ibo)
            self.river_geometry = self.ctx.geometry(
                [self.gl.BufferDescription(vbo, "3f 2f 4f 4f 4f 4f 4f", ["in_pos", "in_tangent", "in_flow", "in_colour",
                                                                         "in_deep", "in_look", "in_ends"])],
                index_buffer=ibo, index_element_size=4, mode=self.ctx.TRIANGLES)
            self.river_allocations += 1
            buffers = self.river_buffers
        buffers[0].write(vertices)
        buffers[1].write(indices)
        self.river_count = len(idx)
        f = river_mod.FLOATS_PER_VERTEX
        xs, ys, zs = data[0::f], data[1::f], data[2::f]
        half = max(data[7::f])  # (a bank is within a half width of its sample: the box needs no more)
        self.river_box = (min(xs) - half, min(ys) - half, min(zs), max(xs) + half, max(ys) + half, max(zs))
        self.mouths, self.mouth_problems = list(joined.values()), problems
        self._mouth_columns = self._columns()
        self.rivers, self._river_key = rivers, (rivers, self.ponds)  # recorded only once made (a failure tries again)

    def _free_rivers(self) -> None:
        if self.river_geometry is not None:
            self.river_geometry.flush()
        for obj in self.river_buffers or ():
            obj.delete()
        self.river_geometry = self.river_buffers = self.river_box = None
        self.rivers, self.river_count, self._river_key = (), 0, None
        self.mouths, self.mouth_problems, self._mouth_columns = [], {}, {}

    def in_view(self, vp: list[list[float]]) -> bool:
        """Whether any water surface is in the picture (its corners' clip-space box overlaps the screen): with none,
        the pass (and its frame copy) is skipped."""
        boxes: list[tuple[float, ...]] = []
        for row in self._key or ():
            reach = math.hypot(row[2], row[3]) + row[21] + 0.16  # turned, with its bank: within this of its centre
            boxes.append((row[0] - reach, row[1] - reach, row[4], row[0] + reach, row[1] + reach, row[4]))
        if self.river_box is not None:
            boxes.append(self.river_box)
        for x0, y0, z0, x1, y1, z1 in boxes:
            pts = []
            for cx, cy, z in ((x0, y0, z0), (x1, y0, z0), (x0, y1, z0), (x1, y1, z0),
                              (x0, y0, z1), (x1, y0, z1), (x0, y1, z1), (x1, y1, z1)):
                c = [vp[r][0] * cx + vp[r][1] * cy + vp[r][2] * z + vp[r][3] for r in (0, 1, 3)]
                if c[2] <= 1e-6:
                    return True  # a corner behind the camera: can't tell cheaply, draw it
                pts.append((c[0] / c[2], c[1] / c[2]))
            if (min(p[0] for p in pts) <= 1 and max(p[0] for p in pts) >= -1
                    and min(p[1] for p in pts) <= 1 and max(p[1] for p in pts) >= -1):
                return True
        return False

    def _free_geometry(self) -> None:
        if self.geometry is not None:
            self.geometry.flush()
        if self.instances is not None:
            self.instances.delete()
        self.geometry = self.instances = None

    def _copy_of(self, fbo: Any, scale: int = 1) -> tuple[Any, Any, Any]:
        """The frame so far, copied (colour and depth): what reflections look into; at ``scale`` 2 a half-size copy
        (a quarter of the memory: ``settings.hd2d.water_reflections`` "half")."""
        size = (max(1, int(fbo.size[0]) // scale), max(1, int(fbo.size[1]) // scale))
        if self.copy is None or tuple(self.copy[0].size) != size:
            self._free_copy()
            ctx = self.ctx
            colour = ctx.texture(size, components=4)
            depth = ctx.depth_texture(size)
            try:
                frame = ctx.framebuffer(color_attachments=[colour], depth_attachment=depth)
            except BaseException:
                colour.delete()
                depth.delete()
                raise
            colour.filter = (ctx.NEAREST, ctx.NEAREST)
            depth.compare_func = None
            depth.filter = (ctx.NEAREST, ctx.NEAREST)
            self.copy = (frame, colour, depth)
        if scale == 1:
            self.ctx.copy_framebuffer(fbo, self.copy[0], depth=True)
        else:  # arcade's copy is same-size only: the same blit, scaled (nearest: depth can't be filtered)
            from pyglet import gl as raw  # noqa: PLC0415

            raw.glBindFramebuffer(raw.GL_READ_FRAMEBUFFER, fbo.glo)
            raw.glBindFramebuffer(raw.GL_DRAW_FRAMEBUFFER, self.copy[0].glo)
            raw.glReadBuffer(raw.GL_COLOR_ATTACHMENT0)
            raw.glDrawBuffer(raw.GL_COLOR_ATTACHMENT0)
            raw.glBlitFramebuffer(0, 0, int(fbo.size[0]), int(fbo.size[1]), 0, 0, size[0], size[1],
                                  raw.GL_COLOR_BUFFER_BIT | raw.GL_DEPTH_BUFFER_BIT, raw.GL_NEAREST)
        return self.copy

    def _free_copy(self) -> None:
        if self.copy is not None:
            for obj in self.copy:
                obj.delete()
        self.copy = None

    def set_terrain(self, terrain: Any, version: int = 0) -> None:
        """The room's sculpted ground (``engine.hd2d.terrain.Terrain``; None: none): its heights as a float texture,
        for water whose shore is the ground. Made again only when ``version`` (the renderer's edit count) changes."""
        key = None if terrain is None else (id(terrain), version)
        if key == self._terrain_key:
            return
        if terrain is not None and self.terrain is not None and self._terrain_key is not None \
                and self._terrain_key[0] == id(terrain):  # the same ground, edited: its heights written in place
            self.terrain[0].write(array("f", [(terrain.base + h) / PX_PER_M for h in terrain.heights]).tobytes())
            self._terrain_key = key
            return
        self._free_terrain()
        self._terrain_key = None
        if terrain is not None:
            data = array("f", [(terrain.base + h) / PX_PER_M for h in terrain.heights])
            tex = self.ctx.texture((terrain.nx + 1, terrain.ny + 1), components=1, dtype="f4", data=data.tobytes())
            tex.filter = (self.ctx.LINEAR, self.ctx.LINEAR)
            tex.wrap_x = tex.wrap_y = self.ctx.CLAMP_TO_EDGE
            self.terrain = (tex, (terrain.origin[0] / PX_PER_M, terrain.origin[1] / PX_PER_M, terrain.cell / PX_PER_M, 0.0))
        self._terrain_key = key

    def _free_terrain(self) -> None:
        if self.terrain is not None:
            self.terrain[0].delete()
        self.terrain = None

    def _uniforms(self, prog: Any, time: float, steps: list[tuple[float, float, float]], rain: float, shelter: Any,
                  light: tuple[float, float, float], sky: tuple[float, float, float]) -> None:
        prog["u_time"] = time
        live = [s for s in steps if 0.0 <= time - s[2] <= STEP_RIPPLE_S][-8:]
        prog["u_steps"] = tuple(v for s in live for v in (s[0], s[1], s[2], 1.0)) + (0.0,) * (4 * (8 - len(live)))
        prog["u_steps_n"] = len(live)
        prog["u_rain"] = rain
        prog["u_light"], prog["u_sky"] = light, sky
        shelter = shelter if self.shelter else None
        prog["u_shelter"] = 1 if shelter is not None else 0
        prog["u_precip"], prog["u_scene"], prog["u_scene_depth"] = 4, 5, 6  # 1 and 2: the lighting's shadow maps
        if shelter is not None:
            shelter.depth.use(4)
            prog["u_precip_vp"] = shelter.vp
        prog["u_terrain"] = 7
        prog["u_has_terrain"] = 1 if self.terrain is not None else 0
        if self.terrain is not None:
            self.terrain[0].use(7)
            prog["u_terrain_box"] = self.terrain[1]
        self._mouth_uniforms(prog)

    def _mouth_uniforms(self, prog: Any) -> None:
        """R4: the rivers flowing into ponds (``self.mouths``), for both programs (the GLSL compiler may leave out
        what one of them doesn't read: set safely)."""
        prog.set_uniform_safe("u_mouths_n", len(self.mouths))
        for name, flat in self._mouth_columns.items():
            prog.set_uniform_array_safe(f"u_mouth_{name}", flat)

    def _columns(self) -> dict[str, list[float]]:
        """The mouths' uniform arrays (MAX_MOUTHS vec4s each, padded), from their ponds' instance rows."""
        if not self.mouths:
            return {}
        columns: dict[str, list[float]] = {name: [] for name in ("at", "info", "rect", "shape", "amp", "phase", "colour",
                                                                  "deep", "look", "kind")}
        for mouth in self.mouths:
            index = int(mouth.pond.id)
            row = self._rows[index]
            waves = 0.045 if row[6] > 1.5 else (0.06 if row[6] > 0.5 else 0.025)  # (the pond shader's, by kind)
            for name, values in (("at", (*mouth.at, *mouth.tangent)), ("info", (mouth.half, mouth.u, float(index), row[4])),
                                 ("rect", row[0:4]), ("shape", (row[5], row[22], row[23], waves)), ("amp", row[24:28]),
                                 ("phase", row[28:32]), ("colour", row[8:12]), ("deep", row[16:20]),
                                 ("look", row[12:16]),
                                 ("kind", (1.0 if row[6] > 1.5 and row[20] == SHORES.index("terrain") else 0.0,
                                           row[7], 0.0, 0.0))):
                columns[name].extend(values)
        return {name: flat + [0.0] * (4 * MAX_MOUTHS - len(flat)) for name, flat in columns.items()}

    def draw_3d(self, vp: tuple[float, ...], eye: tuple[float, float, float], fbo: Any, *, time: float,
                steps: list[tuple[float, float, float]], rain: float, shelter: Any,
                light: tuple[float, float, float], sky: tuple[float, float, float], reflections: str = "full",
                lighting: Any = None) -> None:
        """Into an HD-2D frame already drawn (structures and characters, their depth kept); lit by ``lighting``
        (engine.hd2d.lighting: the room's sun, lamps and their shadows) if given, else by ``light``. ``reflections``
        (``REFLECTIONS``): what's on screen mirrored from a full- or half-size copy of the frame, or the sky only (no
        copy kept)."""
        self.draw_calls = 0
        ponds = self.geometry is not None and self.count > 0
        if not ponds and self.river_geometry is None:
            return
        ctx = self.ctx
        reflect = reflections != "sky"
        screen = (1.0, 1.0)
        if reflect:  # one copy of the frame, for ponds and rivers alike
            _frame, colour, depth = self._copy_of(fbo, 2 if reflections == "half" else 1)
            colour.use(5)
            depth.use(6)
            screen = (float(colour.size[0]), float(colour.size[1]))
        else:
            self._free_copy()
        passes: list[tuple[Any, Any, dict[str, int]]] = []
        if ponds:
            passes.append((self.program, self.geometry, {"instances": self.count}))
        if self.river_geometry is not None:
            passes.append((self.river_program, self.river_geometry, {"vertices": self.river_count}))  # (indices used)
        for prog, _geometry, _count in passes:
            if reflect:
                prog["u_screen"] = screen
            prog["u_reflect"] = 1 if reflect else 0
            prog["u_lit"] = 1 if lighting is not None else 0
            if lighting is not None:
                lighting.bind(prog)
            prog["u_vp"], prog["u_eye"] = vp, eye
            if prog is self.program:
                prog["u_flat"] = 0  # (rivers are HD-2D only: theirs has no flat view)
            self._uniforms(prog, time, steps, rain, shelter, light, sky)
        fbo.use(force=True)  # copy_framebuffer left the copy bound for drawing, unknown to arcade's own record
        fbo.depth_mask = False
        try:
            with ctx.enabled(ctx.BLEND):
                if self.depth_test:
                    ctx.enable(ctx.DEPTH_TEST)
                else:
                    ctx.disable(ctx.DEPTH_TEST)
                for prog, geometry, counts in passes:
                    geometry.render(prog, **counts)
                    self.draw_calls += 1
        finally:
            ctx.enable(ctx.DEPTH_TEST)
            fbo.depth_mask = True

    def draw_2d(self, vp: tuple[float, ...], *, time: float, steps: list[tuple[float, float, float]], rain: float,
                sky: tuple[float, float, float]) -> None:
        """On a 2D room's map, under its characters (the world camera in use)."""
        self.draw_calls = 0
        if self.geometry is None or not self.count:
            return
        prog = self.program
        prog["u_vp"], prog["u_eye"], prog["u_flat"], prog["u_reflect"], prog["u_lit"] = vp, (0.0, 0.0, 0.0), 1, 0, 0
        prog["u_screen"] = (1.0, 1.0)
        self._uniforms(prog, time, steps, rain, None, (1.0, 1.0, 1.0), sky)
        with self.ctx.enabled(self.ctx.BLEND):
            self.geometry.render(prog, instances=self.count)
        self.draw_calls = 1

    def gl_objects(self) -> list[Any]:
        return [o for o in (self.program, self.quad, self.instances, *(self.copy or ()),
                            self.terrain[0] if self.terrain else None, self.river_program,
                            *(self.river_buffers or ())) if o is not None]

    def memory_bytes(self) -> int:
        size = (self.instances.size if self.instances is not None else 0) + (self.quad.size if self.quad else 0)
        if self.copy is not None:
            w, h = self.copy[1].size
            size += w * h * 8
        if self.terrain is not None:
            w, h = self.terrain[0].size
            size += w * h * 4
        size += sum(b.size for b in self.river_buffers or ())
        return int(size)

    def release(self) -> None:
        """Free every GPU object (also of a partly made layer); a second call does nothing."""
        self._free_geometry()
        self._free_copy()
        self._free_terrain()
        self._terrain_key = None
        self._free_rivers()
        for obj in (self.quad, self.program, self.river_program):
            if obj is not None:
                obj.delete()
        self.quad = self.program = self.river_program = None
        self._key, self.count = None, 0


def active(window: Any, entity: Any) -> bool:
    """Whether a water object is there now: its "Show when" flags (Studio keeps them in its ConditionalActivator;
    older objects at the entity's own require/forbid flags). A water object has no picture, so its sprite is never
    ``visible``: that isn't the test."""
    for behaviour in getattr(entity, "mesh_behaviours_runtime", None) or ():
        if type(behaviour).__name__ == "ConditionalActivator":
            return bool(behaviour._requirements_met())
    get_flag = getattr(window, "get_flag", None)
    if not callable(get_flag):
        return True
    from engine.scene_entity_gating import runtime_entity_passes_flag_gates  # noqa: PLC0415

    return runtime_entity_passes_flag_gates(entity, get_flag=get_flag)


def bodies_of(window: Any) -> list[Body]:
    """The room's water surfaces there now (``active``)."""
    return [b for b in (getattr(window, "water_bodies", None) or []) if active(window, b.entity)]


def draw_2d(window: Any) -> None:
    """A 2D room's water, after its ground and before its characters (``engine.scene_controller_parts.rendering``)."""
    bodies = bodies_of(window)
    if (not bodies or getattr(window, "hd2d_renderer", None) is not None or getattr(window, "ctx", None) is None
            or getattr(window, "scene_water_error", None)):
        return
    try:
        _draw_2d(window, bodies)
    except Exception as exc:  # the driver refused it: no water in this room (its next load tries again)
        window.scene_water_error = f"water: {exc}"
        from engine.logging_tools import get_logger  # noqa: PLC0415

        get_logger(__name__).error("[Mesh][Water] %s (water is off in this room)", window.scene_water_error)
        release(window)


def _draw_2d(window: Any, bodies: list[Body]) -> None:
    layer = getattr(window, "scene_water", None)
    if layer is None:
        import engine.optional_arcade as optional_arcade  # noqa: PLC0415

        layer = window.scene_water = WaterLayer(window.ctx, gl=optional_arcade.arcade.gl)
    layer.set_bodies(bodies)
    ctx = window.ctx
    particles = getattr(window, "scene_particles", None)
    rain = rain_rate(particles.effects, particles.enabled) if particles is not None else 0.0
    layer.draw_2d(tuple(ctx.projection_matrix @ ctx.view_matrix), time=float(getattr(window, "water_time", 0.0)),
                  steps=list(getattr(window, "water_steps", None) or []), rain=rain, sky=(0.55, 0.68, 0.82))


def release(window: Any) -> None:
    layer = getattr(window, "scene_water", None)
    if layer is not None:
        layer.release()
    window.scene_water = None
