"""Environmental particles (Milestone 18A): rain, snow and windborne leaves about the camera, drawn in an HD-2D room's
3D world (real positions, depth-tested against its buildings, characters and floors) and, when a 2D room asks for
them, over its map under its own lighting. The room's other effects (``engine.particles``) are untouched.

A room asks with ``settings.particles``, a list of effects (``parse_particles``):

    "particles": [{"preset": "rain", "count": 3000, "wind": [1.2, 0.0]},
                  {"preset": "wind", "count": 150, "gust": 0.8, "seed": 4}]

How they move (stateless, on the GPU): each particle is a fixed seed (a place in a box of the effect's ``area``, a
phase, a look and a speed); the vertex shader computes where it is at time t from the seed alone (falling, drifting,
blown), and wraps it into the box, which follows the camera. A particle keeps its world position as the camera moves
(the box only decides which copy of the endless repeating pattern is drawn), so it is never a screen overlay. Nothing
is spawned, stepped or freed per frame: per effect, one static buffer of seeds and one draw call; the CPU sets a few
uniforms. The same seed and time always give the same picture (replays, tests).

Pixel art: every particle is a picture from a small procedural atlas at the art's 32 px per metre, sampled nearest,
binary alpha (the effect's opacity is the only translucency).
"""

from __future__ import annotations

import math
import random
from array import array
from dataclasses import dataclass
from typing import Any

PX_PER_M = 32.0
MAX_EFFECTS = 4
MAX_COUNT = 20000  # per effect
_KEYS = {"preset", "count", "speed", "wind", "gust", "lifetime", "seed", "area", "opacity", "enabled"}


class SceneParticlesError(ValueError):
    """``settings.particles`` that can't be used (the room still loads, without them)."""


@dataclass(frozen=True)
class ParticleEffect:
    preset: str  # "rain" | "snow" | "wind"
    count: int  # particles in its box
    speed: float  # times the preset's own fall (rain, snow) or drift (wind) speed
    wind: tuple[float, float]  # m/s east, north
    gust: float  # 0..1: how much the wind swells and drops (all presets; strongest on "wind")
    lifetime: float  # s: how long a windborne leaf is seen before it fades and turns up elsewhere ("wind")
    seed: int
    area: tuple[float, float, float]  # m: the box about the camera: across, along the view, high
    opacity: float  # 0..1
    enabled: bool = True


@dataclass(frozen=True)
class _Preset:
    kind: int  # the shader's branch
    count: int
    fall: float  # m/s down (rain, snow); for "wind" the wind's default strength
    wind: tuple[float, float]
    gust: float
    lifetime: float
    area: tuple[float, float, float]
    opacity: float
    # its pictures: (x, y, w, h) px in the atlas, and how often each is chosen
    variants: tuple[tuple[int, int, int, int], ...]
    weights: tuple[float, ...]
    impact: float = 0.0  # s a landed particle shows where it met a surface (Milestone 18B; 0: it never lands)


# A raindrop's splash where it lands (Milestone 18B): three frames in the atlas, (x, y, w, h) px, played over its
# impact time; a snowflake settles as its own picture, fading.
SPLASH = ((12, 4, 3, 2), (16, 4, 5, 2), (22, 4, 7, 2))
EXPOSURES = ("outdoor", "indoor")  # settings.weather_exposure: an indoor room gets no weather (rain, snow, leaves)


PRESETS: dict[str, _Preset] = {
    "rain": _Preset(0, 3000, 9.0, (0.8, 0.0), 0.2, 0.0, (30.0, 34.0, 12.0), 0.55,
                    ((0, 0, 1, 10), (2, 0, 1, 14)), (0.6, 0.4), impact=0.15),
    "snow": _Preset(1, 2000, 1.1, (0.3, 0.0), 0.3, 0.0, (30.0, 34.0, 10.0), 0.9,
                    ((4, 0, 2, 2), (7, 0, 3, 3)), (0.65, 0.35), impact=1.5),
    "wind": _Preset(2, 400, 3.2, (3.2, 0.6), 0.7, 6.0, (30.0, 34.0, 4.0), 1.0,
                    ((0, 16, 5, 4), (6, 16, 5, 4), (12, 16, 4, 3), (17, 16, 2, 1)), (0.35, 0.3, 0.25, 0.1)),
}


def _number(value: Any, what: str, lo: float, hi: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lo <= value <= hi:
        raise SceneParticlesError(f"{what} must be a number from {lo:g} to {hi:g} (got {value!r})")
    return float(value)


def _pair(value: Any, what: str, lim: float) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise SceneParticlesError(f"{what} must be two numbers, [east, north] m/s (got {value!r})")
    return (_number(value[0], what, -lim, lim), _number(value[1], what, -lim, lim))


def parse_particles(raw: Any) -> tuple[ParticleEffect, ...]:
    """A room's ``settings.particles`` (None or a list of effects) checked and completed from each preset."""
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise SceneParticlesError("particles must be a list of effects")
    if len(raw) > MAX_EFFECTS:
        raise SceneParticlesError(f"a room has at most {MAX_EFFECTS} particle effects (got {len(raw)})")
    out = []
    for i, item in enumerate(raw):
        where = f"particles[{i}]"
        if not isinstance(item, dict):
            raise SceneParticlesError(f"{where} must be an object like {{\"preset\": \"rain\"}}")
        unknown = set(item) - _KEYS
        if unknown:
            raise SceneParticlesError(f"{where}: unknown setting(s) {', '.join(sorted(unknown))}")
        preset = PRESETS.get(str(item.get("preset")))
        if preset is None:
            raise SceneParticlesError(f"{where}.preset must be one of {', '.join(PRESETS)} (got {item.get('preset')!r})")
        count = item.get("count", preset.count)
        if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= MAX_COUNT:
            raise SceneParticlesError(f"{where}.count must be a whole number from 0 to {MAX_COUNT} (got {count!r})")
        area = item.get("area", list(preset.area))
        if not isinstance(area, (list, tuple)) or len(area) != 3:
            raise SceneParticlesError(f"{where}.area must be [across, along, high] metres")
        enabled = item.get("enabled", True)
        if not isinstance(enabled, bool):
            raise SceneParticlesError(f"{where}.enabled must be true or false")
        seed = item.get("seed", 1)
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise SceneParticlesError(f"{where}.seed must be a whole number")
        out.append(ParticleEffect(
            preset=str(item["preset"]), count=count, speed=_number(item.get("speed", 1.0), f"{where}.speed", 0.0, 5.0),
            wind=_pair(item.get("wind", list(preset.wind)), f"{where}.wind", 30.0),
            gust=_number(item.get("gust", preset.gust), f"{where}.gust", 0.0, 1.0),
            lifetime=_number(item.get("lifetime", preset.lifetime or 1.0), f"{where}.lifetime", 0.5, 60.0),
            seed=seed, area=(_number(area[0], f"{where}.area", 4.0, 120.0), _number(area[1], f"{where}.area", 4.0, 120.0),
                             _number(area[2], f"{where}.area", 1.0, 40.0)),
            opacity=_number(item.get("opacity", preset.opacity), f"{where}.opacity", 0.0, 1.0), enabled=enabled))
    return tuple(out)


def parse_exposure(raw: Any) -> str:
    """A room's ``settings.weather_exposure``: "outdoor" (the default) or "indoor" (no weather)."""
    if raw is None:
        return "outdoor"
    if raw not in EXPOSURES:
        raise SceneParticlesError(f"weather_exposure must be one of {', '.join(EXPOSURES)} (got {raw!r})")
    return str(raw)


def seeds(effect: ParticleEffect) -> array:
    """The effect's particles, 6 floats each: a place in its box (x, y, z in 0..1), a phase (0..1), a picture
    (variant index) and a speed factor (0.8..1.2). Deterministic: the same effect gives the same numbers."""
    preset = PRESETS[effect.preset]
    rng = random.Random(effect.seed * 7919 + preset.kind)
    variants = list(range(len(preset.variants)))
    data = array("f")
    for _ in range(effect.count):
        data.extend((rng.random(), rng.random(), rng.random(), rng.random(),
                     float(rng.choices(variants, preset.weights)[0]), 0.8 + 0.4 * rng.random()))
    return data


def atlas_image() -> Any:
    """The particles' pictures (32 x 24 px, drawn in code): rain streaks, snowflakes, leaves and a bit of debris."""
    from PIL import Image  # noqa: PLC0415

    image = Image.new("RGBA", (32, 24), (0, 0, 0, 0))
    px = image.load()
    assert px is not None
    for x0, height in ((0, 10), (2, 14)):  # rain: a pale streak, brighter at its head (the bottom)
        for y in range(height):
            px[x0, y] = (214, 228, 246, 255) if y >= height - 3 else (170, 190, 220, 255)
    for x, y in ((4, 0), (5, 0), (4, 1), (5, 1)):  # snow: a 2 px flake and a 3 px cross
        px[x, y] = (246, 248, 255, 255)
    for x, y in ((8, 0), (7, 1), (8, 1), (9, 1), (8, 2)):
        px[x, y] = (250, 252, 255, 255) if (x, y) == (8, 1) else (226, 232, 246, 255)
    leaf = ("..##.", ".####", "####.", ".##..")  # leaves 5 x 4: green, amber; a smaller brown one 4 x 3
    for x0, (dark, light) in ((0, ((74, 112, 46, 255), (112, 150, 64, 255))), (6, ((150, 92, 34, 255), (204, 142, 58, 255)))):
        for y, row in enumerate(leaf):
            for x, ch in enumerate(row):
                if ch == "#":
                    px[x0 + x, 16 + y] = light if (x + y) % 3 else dark
    for y, row in enumerate((".##.", "####", ".#..")):
        for x, ch in enumerate(row):
            if ch == "#":
                px[12 + x, 16 + y] = (120, 82, 48, 255) if x % 2 else (96, 64, 38, 255)
    px[17, 16], px[18, 16] = (120, 112, 98, 255), (98, 90, 78, 255)  # debris: a 2 x 1 fleck
    for (x0, y0, _w, _h), rows in zip(SPLASH, ((".#.", "#.#"), ("#...#", ".#.#."), ("#.....#", ".#...#."))):
        for y, row in enumerate(rows):  # a raindrop's splash: a crown, spreading, falling apart
            for x, ch in enumerate(row):
                if ch == "#":
                    px[x0 + x, y0 + y] = (214, 228, 246, 255) if y == 0 else (180, 200, 228, 255)
    return image


def box_for_3d(target: tuple[float, float, float], pitch: float, area: tuple[float, float, float],
               ground: float, below: float = 0.0) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """The box (min corner, size; m) particles fill about the camera's target, for a camera ``pitch`` degrees down:
    from the ground up ``area[2]``, across ``area[0]``, and far enough south that a particle high up, which the
    picture shows further down, still fills the bottom of the picture. ``below``: how far it reaches under the
    ground, so a drop that lands on the ground goes on long enough (unseen) to show its splash first."""
    w, d, h = area
    back = h / max(0.2, math.tan(math.radians(pitch)))
    return (target[0] - w / 2, target[1] - d / 2 - back, ground - below), (w, d + back, h + below)


def fall_of(effect: ParticleEffect) -> tuple[float, float, float] | None:
    """The direction (m/s) the effect's particles fall in, on average (no gusts, no sway); None for one that doesn't
    fall (windborne leaves, or a speed of 0)."""
    preset = PRESETS[effect.preset]
    fall = preset.fall * effect.speed
    if preset.kind == 2 or fall <= 0.0:
        return None
    return (effect.wind[0], effect.wind[1], -fall)


def impact_reach(effect: ParticleEffect) -> float:
    """How far (m) under a surface its fastest particle goes while its impact shows (1.2: the speed spread)."""
    fall = fall_of(effect)
    return 0.0 if fall is None else 1.2 * math.sqrt(sum(c * c for c in fall)) * PRESETS[effect.preset].impact + 0.25


def box_for_2d(centre: tuple[float, float], view: tuple[float, float], area: tuple[float, float, float]) -> \
        tuple[tuple[float, float, float], tuple[float, float, float]]:
    """In a 2D room a particle at (x, y, z) is drawn at (x, y + z) on the map: the box covers the view (m), and
    reaches ``area[2]`` further south for the highest ones."""
    w, d, h = max(area[0], view[0] + 4.0), max(area[1], view[1] + 4.0), area[2]
    return (centre[0] - w / 2, centre[1] - d / 2 - h, 0.0), (w, d + h, h)


VS = """
#version 330
uniform mat4 u_vp; uniform float u_time; uniform vec3 u_box_min; uniform vec3 u_box_size;
uniform int u_kind; uniform float u_fall; uniform vec2 u_wind; uniform float u_gust; uniform float u_life;
uniform vec3 u_right; uniform vec3 u_up; uniform int u_flat; uniform vec4 u_variants[4]; uniform vec2 u_atlas;
// Milestone 18B. Where it meets the world: u_shelter 1 when this effect has a precipitation map (HD-2D); impacts
// shown for u_impact s (a splash's frames, or a settling flake); the room's rectangle (m) it's kept inside.
uniform int u_shelter; uniform sampler2D u_precip; uniform mat4 u_precip_vp; uniform float u_precip_depth_m;
uniform vec3 u_precip_dir; uniform float u_impact; uniform vec4 u_splash[3]; uniform vec3 u_toward_eye;
uniform int u_clip; uniform vec4 u_bounds; uniform int u_probe;
in vec2 in_corner; in vec4 in_seed; in vec2 in_var;
out vec2 v_uv; out float v_alpha; flat out vec4 v_probe;
float hash(float n) { return fract(sin(n) * 43758.5453); }
float g_alpha, g_flip, g_bob;  // the particle's own fade, flutter and bob (leaves), set by place()
// Where the particle is at time t (m, before the box's wrap): a pure function of its seed and the time.
vec3 place(float t) {
    float phase = in_seed.w, sp = in_var.y;
    vec3 w = in_seed.xyz * u_box_size;  // its place in the endless repeating pattern
    g_alpha = 1.0; g_flip = 1.0; g_bob = 0.0;
    // the wind, swelling and dropping: its integral, so speed stays bounded
    float drift = t + u_gust * (cos(phase * 6.2832) - cos(t * 0.7 + phase * 6.2832)) / 0.7;
    if (u_kind == 0) {          // rain: straight down, slanted by the wind
        w += vec3(u_wind * drift, -u_fall * t) * sp;
    } else if (u_kind == 1) {   // snow: slow, swaying
        w += vec3(u_wind * drift, -u_fall * t) * sp;
        w.x += 0.35 * sin(t * 0.9 * sp + phase * 6.2832);
        w.y += 0.25 * sin(t * 0.7 * sp + phase * 4.0);
    } else {                     // windborne: carried along, bobbing, fluttering; seen for u_life s, then elsewhere
        float life = t / u_life + phase, cycle = floor(life), age = fract(life);
        w += vec3(hash(cycle * 12.9898 + phase * 78.233), hash(cycle * 39.346 + phase * 11.135), 0.0) * u_box_size;
        w += vec3(u_wind * drift * sp, 0.0);
        g_bob = 0.35 * sin(t * 2.3 * sp + phase * 6.2832);  // after the wrap: a leaf never jumps floor to top
        g_alpha = smoothstep(0.0, 0.12, age) * (1.0 - smoothstep(0.82, 1.0, age));
        g_flip = sin(t * 5.0 * sp + phase * 6.2832) < 0.0 ? -1.0 : 1.0;
    }
    return w;
}
vec3 wrapped(vec3 w) { return u_box_min + mod(w - u_box_min, u_box_size); }
// How fast a falling particle (rain, snow) moves at time t (m/s): place()'s derivative, gusts and sway included.
vec3 velocity(float t) {
    float phase = in_seed.w, sp = in_var.y;
    vec3 v = vec3(u_wind * (1.0 + u_gust * sin(t * 0.7 + phase * 6.2832)), -u_fall) * sp;
    if (u_kind == 1) {
        v.x += 0.35 * 0.9 * sp * cos(t * 0.9 * sp + phase * 6.2832);
        v.y += 0.25 * 0.7 * sp * cos(t * 0.7 * sp + phase * 4.0);
    }
    return v;
}
// How far (m, along the fall) a point is past the first surface the fall meets; negative: above it (or no surface:
// outside the map, or open to the bottom of the world).
float past_surface(vec3 p) {
    vec3 q = (u_precip_vp * vec4(p, 1.0)).xyz * 0.5 + 0.5;
    if (q.x < 0.0 || q.x > 1.0 || q.y < 0.0 || q.y > 1.0) return -1.0;
    float d = texture(u_precip, q.xy).r;
    return d >= 1.0 ? -1.0 : (q.z - d) * u_precip_depth_m;
}
void main() {
    float t = u_time, sp = in_var.y;
    vec3 p = wrapped(place(t));
    float alpha = g_alpha, flip = g_flip;
    vec4 vr = u_variants[int(in_var.x + 0.5)];
    bool landed = false;
    float age = 0.0;
    if (u_kind != 2 && u_impact > 0.0 && (u_shelter == 1 || u_flat == 1)) {
        if (u_flat == 1) {  // 2D: the ground is the box's floor; a drop just past it is at the top (faded): show where
            age = (u_box_min.z + u_box_size.z - p.z) / max(u_fall * sp, 1e-3);  // ... it landed instead
            if (age < u_impact) {
                vec3 at = wrapped(place(t - age + 1e-3));
                p = vec3(at.xy, u_box_min.z);
                landed = true;
            } else {
                alpha *= clamp((age - u_impact) / 0.25, 0.0, 1.0);  // then the next drop fades in
            }
        } else {
            float s = past_surface(p);
            if (s >= 0.0) {  // it met a surface (or is under one: it met that one first)
                age = s / max(dot(velocity(t), u_precip_dir), 1e-3);  // how long ago, at the speed it has now
                if (age < u_impact) {  // where it landed: back along its own fall, from where it was then
                    vec3 then = wrapped(place(t - age));
                    float off = past_surface(then);
                    p = then - u_precip_dir * max(off, 0.0);
                    landed = abs(off) < 0.12;  // a gust carried it across an edge since: no splash (none in the
                    alpha = landed ? alpha : 0.0;  // ... wrong place), it simply isn't seen
                } else {
                    alpha = 0.0;  // landed earlier, or sheltered: gone until it comes round again
                }
            }
        }
    }
    flip = landed ? 1.0 : flip;
    alpha = landed ? (u_kind == 1 ? 1.0 - smoothstep(0.4, 1.0, age / u_impact) : 1.0) : alpha;
    vec2 edge = min(p.xy - u_box_min.xy, u_box_min.xy + u_box_size.xy - p.xy);
    alpha *= clamp(min(edge.x, edge.y) / 1.5, 0.0, 1.0);  // fade at the box's sides: wrapping never pops in view
    if (u_kind == 2) {  // leaves keep 0.35 m clear of the floor and top, and bob within that
        p.z = u_box_min.z + 0.35 + (p.z - u_box_min.z) * (u_box_size.z - 0.7) / u_box_size.z + g_bob;
    } else if (!landed) {  // rain and snow fade in at the top (where a fallen one comes back)
        alpha *= clamp((u_box_min.z + u_box_size.z - p.z) / 1.5, 0.0, 1.0);
    }
    if (landed && u_kind == 0) {
        vr = u_splash[int(min(2.0, floor(age / u_impact * 3.0)))];
    }
    vec2 flat_at = u_flat == 1 ? vec2(p.x, p.y + p.z) : p.xy;  // where it shows on a 2D map, or stands in 3D
    if (u_clip == 1 && (flat_at.x < u_bounds.x || flat_at.x > u_bounds.z || flat_at.y < u_bounds.y || flat_at.y > u_bounds.w)) {
        alpha = 0.0;  // outside the room
    }
    vec2 size = vr.zw / 32.0;  // the art's 32 px per metre
    vec3 across = u_right * size.x, along = u_up * size.y;
    if (u_kind == 0 && !landed && u_probe == 0) {  // a streak lies along its fall (diagnostics: any view sees it)
        vec3 fall = vec3(u_wind * sp, -u_fall * sp);
        along = -normalize(fall) * size.y;
    }
    // a landed one stands on the surface facing the camera, a few cm towards it (the surface doesn't hide it)
    vec3 base = landed && u_flat == 0 ? p + u_toward_eye * 0.06 : p;
    vec3 world = base + across * in_corner.x * flip + along * in_corner.y;
    v_uv = (vr.xy + vec2(in_corner.x + 0.5, 1.0 - in_corner.y) * vr.zw) / u_atlas;
    v_alpha = alpha;
    v_probe = vec4(p, landed ? -float(gl_InstanceID) - 1.0 : float(gl_InstanceID));  // diagnostics: where, which
    gl_Position = alpha <= 0.0 ? vec4(2.0, 2.0, 2.0, 1.0)  // not drawn: off the picture
                : u_flat == 1 ? u_vp * vec4(world.x * 32.0, (world.y + world.z) * 32.0, 0.0, 1.0)
                              : u_vp * vec4(world, 1.0);
}
"""
FS = """
#version 330
uniform sampler2D u_tex; uniform vec3 u_light; uniform float u_opacity; uniform int u_probe;
in vec2 v_uv; in float v_alpha; flat in vec4 v_probe; out vec4 f_color;
void main() {
    vec4 c = texture(u_tex, v_uv);
    float a = (v_probe.w < 0.0 ? max(u_opacity, 0.85) : u_opacity) * v_alpha;  // a splash shows a little firmer
    if (c.a < 0.5 || a < 0.004) discard;  // binary alpha, like every Mesh picture
    // diagnostics (u_probe 1): the particle's world position (m) and its id (negative: landed), into a float target
    f_color = u_probe == 1 ? v_probe : vec4(c.rgb * u_light, a);
}
"""


class ParticleLayer:
    """A room's particle effects on the GPU: one program, one atlas, one quad, and per effect a buffer of seeds and a
    draw call. ``update`` advances its clock; ``draw_3d`` / ``draw_2d`` draw every enabled effect; ``release`` frees
    every GPU object (room change, window close)."""

    def __init__(self, ctx: Any, effects: tuple[ParticleEffect, ...], *, gl: Any,
                 bounds: tuple[float, float, float, float] | None = None) -> None:
        """``bounds``: the room's rectangle (x0, y0, x1, y1 m) particles are kept inside, if it has one."""
        self.ctx, self.effects, self.time, self.bounds = ctx, effects, 0.0, bounds
        self.enabled = [e.enabled for e in effects]
        self.depth_test = True  # False only to show what depth testing hides (diagnostics)
        self.shelter = True  # False only to show Stage 18A's behaviour beside 18B's (diagnostics: negative controls)
        self.probe = False  # True: write each particle's world position and id (diagnostics; a float target)
        self.draw_calls = 0
        self.program: Any = None
        self.texture: Any = None
        self.quad: Any = None
        self.buffers: list[Any] = []
        self.geometries: list[Any] = []
        try:  # one GPU object after another: if one fails, free those already made (not left to GC), then raise
            self.program = ctx.program(vertex_shader=VS, fragment_shader=FS)
            image = atlas_image()
            self.texture = ctx.texture(image.size, components=4, data=image.tobytes(),
                                       filter=(ctx.NEAREST, ctx.NEAREST))
            self.quad = ctx.buffer(data=array("f", [-0.5, 0.0, 0.5, 0.0, -0.5, 1.0, 0.5, 1.0]).tobytes())
            for effect in effects:
                buffer = ctx.buffer(data=seeds(effect).tobytes()) if effect.count else None
                self.buffers.append(buffer)
                self.geometries.append(None if buffer is None else ctx.geometry(
                    [gl.BufferDescription(self.quad, "2f", ["in_corner"]),
                     gl.BufferDescription(buffer, "4f 2f", ["in_seed", "in_var"], instanced=True)],
                    mode=ctx.TRIANGLE_STRIP))
        except BaseException:
            self.release()
            raise
        self.uniforms = [self._uniforms(e) for e in effects]  # per effect, fixed: set as they are each frame

    @staticmethod
    def _uniforms(effect: ParticleEffect) -> dict[str, Any]:
        preset = PRESETS[effect.preset]
        variants = list(preset.variants) + [(0, 0, 1, 1)] * (4 - len(preset.variants))
        windborne = preset.kind == 2
        return {"u_variants": tuple(float(v) for variant in variants for v in variant), "u_kind": preset.kind,
                "u_fall": 0.0 if windborne else preset.fall * effect.speed,
                "u_wind": tuple(c * effect.speed for c in effect.wind) if windborne else effect.wind,
                "u_gust": effect.gust, "u_life": effect.lifetime, "u_opacity": effect.opacity,
                "u_impact": preset.impact if fall_of(effect) is not None else 0.0}

    def visible(self) -> bool:
        return any(on and g is not None for on, g in zip(self.enabled, self.geometries))

    def update(self, delta_time: float) -> None:
        self.time += max(0.0, float(delta_time))

    def set_enabled(self, index: int, on: bool) -> None:
        self.enabled[index] = bool(on)

    def memory_bytes(self) -> int:
        if self.program is None:  # released
            return 0
        return int(sum(b.size for b in self.buffers if b is not None) + self.quad.size
                   + self.texture.width * self.texture.height * 4)

    def gl_objects(self) -> list[Any]:
        return [self.program, self.texture, self.quad, *(b for b in self.buffers if b is not None)]

    def release(self) -> None:
        """Free every GPU object this layer made (also a partly made one); a second call does nothing."""
        for geometry in self.geometries:
            if geometry is not None:
                geometry.flush()  # its vertex arrays
        for obj in (*self.buffers, self.quad, self.texture, self.program):
            if obj is not None:
                obj.delete()
        self.buffers, self.geometries = [], []
        self.quad = self.texture = self.program = None

    def _draw(self, vp: tuple[float, ...], boxes: list[tuple[tuple[float, float, float], tuple[float, float, float]]],
              right: tuple[float, float, float], up: tuple[float, float, float], light: tuple[float, float, float],
              flat: bool, maps: list[Any] | None = None, toward_eye: tuple[float, float, float] = (0.0, 0.0, 0.0),
              bounds: tuple[float, float, float, float] | None = None) -> None:
        prog = self.program
        prog["u_vp"] = vp
        prog["u_time"] = self.time
        prog["u_right"], prog["u_up"], prog["u_flat"] = right, up, 1 if flat else 0
        prog["u_atlas"] = (32.0, 24.0)
        prog["u_light"] = light
        prog["u_tex"], prog["u_precip"] = 0, 1
        prog["u_splash"] = tuple(float(v) for frame in SPLASH for v in frame)
        prog["u_toward_eye"] = toward_eye
        prog["u_clip"] = 1 if bounds is not None else 0
        prog["u_bounds"] = bounds or (0.0, 0.0, 0.0, 0.0)
        prog["u_probe"] = 1 if self.probe else 0
        self.texture.use(0)
        self.draw_calls = 0
        for i, (effect, on, geometry, uniforms, (box_min, box_size)) in enumerate(zip(
                self.effects, self.enabled, self.geometries, self.uniforms, boxes)):
            if not on or geometry is None:
                continue
            for name, value in uniforms.items():
                prog[name] = value
            shelter = maps[i] if maps is not None else None
            prog["u_shelter"] = 1 if shelter is not None and self.shelter else 0
            if shelter is not None:
                shelter.depth.use(1)
                prog["u_precip_vp"], prog["u_precip_depth_m"] = shelter.vp, shelter.depth_m
                prog["u_precip_dir"] = shelter.direction
            prog["u_box_min"], prog["u_box_size"] = box_min, box_size
            geometry.render(prog, instances=effect.count)
            self.draw_calls += 1

    def draw_3d(self, vp: tuple[float, ...], camera: Any, ground: float, light: tuple[float, float, float],
                fbo: Any, maps: list[Any] | None = None) -> None:
        """Into an HD-2D frame already drawn (its depth kept): depth-tested, not writing depth, blended. ``maps``:
        per effect, its precipitation map (engine.hd2d.precipitation) or None: with one, it stops at surfaces and
        under shelter, and shows where it landed; without, it falls as in Stage 18A."""
        self.draw_calls = 0
        if not self.visible():
            return
        ctx = self.ctx
        eye, target = camera.eye(), camera.target
        f = [target[i] - eye[i] for i in range(3)]
        n = math.sqrt(sum(v * v for v in f)) or 1.0
        f = [v / n for v in f]
        s = [f[1], -f[0], 0.0]
        n = math.hypot(s[0], s[1]) or 1.0
        s = [s[0] / n, s[1] / n, 0.0]
        u = (s[1] * f[2] - s[2] * f[1], s[2] * f[0] - s[0] * f[2], s[0] * f[1] - s[1] * f[0])
        boxes = [box_for_3d(target, camera.pitch, e.area, ground,
                            impact_reach(e) if maps is not None and maps[i] is not None and self.shelter else 0.0)
                 for i, e in enumerate(self.effects)]
        fbo.depth_mask = False
        try:
            with ctx.enabled(ctx.BLEND) if not self.probe else ctx.enabled_only(ctx.DEPTH_TEST):
                if not self.depth_test:
                    ctx.disable(ctx.DEPTH_TEST)
                self._draw(vp, boxes, (s[0], s[1], 0.0), u, light, flat=False, maps=maps,
                           toward_eye=(-f[0], -f[1], -f[2]), bounds=self.bounds)
        finally:
            ctx.enable(ctx.DEPTH_TEST)
            fbo.depth_mask = True

    def draw_2d(self, vp: tuple[float, ...], centre_m: tuple[float, float], view_m: tuple[float, float]) -> None:
        """Over a 2D room's map (the world camera in use): x across, y + z up the map; drops land on the ground
        (splashes, settling flakes) and stay inside the room's map (``bounds``) when it has one."""
        self.draw_calls = 0
        if not self.visible():
            return
        ctx = self.ctx
        boxes = [box_for_2d(centre_m, view_m, e.area) for e in self.effects]
        with ctx.enabled(ctx.BLEND) if not self.probe else ctx.enabled_only():
            self._draw(vp, boxes, (1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (1.0, 1.0, 1.0), flat=True, bounds=self.bounds)


# --- a 2D room's particles (window.scene_particles); an HD-2D room's belong to its renderer --------------------------

def configure(window: Any, settings: Any, scene: Any = None) -> None:
    """Called while a room loads, after its HD-2D renderer (if any): a 2D room that asks for particles gets a layer."""
    release(window)
    window.scene_particles_error = None
    window.scene_particles_notice = None
    settings = settings if isinstance(settings, dict) else {}
    raw = settings.get("particles")
    try:
        indoor = parse_exposure(settings.get("weather_exposure")) == "indoor"  # checked even without particles
        if raw is None:
            return
        effects = parse_particles(raw)
        if indoor and effects:
            # Milestone 18B: weather is the outdoors'; an indoor room gets none, whatever asks for it
            window.scene_particles_notice = (f"This room is indoors (weather_exposure), so its "
                                             f"{', '.join(e.preset for e in effects)} is not shown.")
            effects = ()
        renderer = getattr(window, "hd2d_renderer", None)
        if renderer is not None:
            renderer.set_particles(effects, bounds=room_bounds_2d(settings, scene))
        elif effects and getattr(window, "ctx", None) is not None:
            import engine.optional_arcade as optional_arcade  # noqa: PLC0415

            window.scene_particles = ParticleLayer(window.ctx, effects, gl=optional_arcade.arcade.gl,
                                                   bounds=room_bounds_2d(settings, scene))
    except Exception as exc:  # bad settings, or a driver that can't build them: the room still loads, without them
        window.scene_particles_error = str(exc)
        from engine.logging_tools import get_logger  # noqa: PLC0415

        get_logger(__name__).error("[Mesh][Particles] this room's particles are off: %s", exc)


def room_bounds_2d(settings: dict, scene: Any) -> tuple[float, float, float, float] | None:
    """A 2D room's rectangle (m): its settings' world size, else its map's (tiles x tile size); None: neither."""
    def number(v: Any) -> bool:
        return isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0

    size: tuple[Any, Any] = (settings.get("world_width"), settings.get("world_height"))
    tilemap = scene.get("tilemap") if isinstance(scene, dict) else None
    if not all(number(v) for v in size) and isinstance(tilemap, dict):
        try:
            size = (float(tilemap["width"]) * float(tilemap["tilewidth"]),
                    float(tilemap["height"]) * float(tilemap["tileheight"]))
        except (KeyError, TypeError, ValueError):
            return None
    return (0.0, 0.0, float(size[0]) / PX_PER_M, float(size[1]) / PX_PER_M) if all(number(v) for v in size) else None


def release(window: Any) -> None:
    layer = getattr(window, "scene_particles", None)
    if layer is not None:
        layer.release()
    window.scene_particles = None


def update(window: Any, delta_time: float) -> None:
    layer = getattr(window, "scene_particles", None)
    if layer is not None:
        layer.update(delta_time)


def draw_2d(window: Any) -> None:
    """A 2D room's particles, with the world camera in use (its projection and view)."""
    layer = getattr(window, "scene_particles", None)
    if layer is None:
        return
    if layer.bounds is None:  # a map from its own file: its size is known once it has loaded
        size = (getattr(window, "world_width", None), getattr(window, "world_height", None))
        layer.bounds = room_bounds_2d({"world_width": size[0], "world_height": size[1]}, None)
    ctx = window.ctx
    vp = ctx.projection_matrix @ ctx.view_matrix
    camera = getattr(window, "camera", None)
    position = getattr(camera, "position", (window.width / 2, window.height / 2))
    zoom = float(getattr(camera, "zoom", 1.0) or 1.0)
    view = (window.width / zoom / PX_PER_M, window.height / zoom / PX_PER_M)
    layer.draw_2d(tuple(vp), (float(position[0]) / PX_PER_M, float(position[1]) / PX_PER_M), view)
