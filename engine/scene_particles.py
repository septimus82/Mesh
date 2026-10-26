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


PRESETS: dict[str, _Preset] = {
    "rain": _Preset(0, 3000, 9.0, (0.8, 0.0), 0.2, 0.0, (30.0, 34.0, 12.0), 0.55,
                    ((0, 0, 1, 10), (2, 0, 1, 14)), (0.6, 0.4)),
    "snow": _Preset(1, 2000, 1.1, (0.3, 0.0), 0.3, 0.0, (30.0, 34.0, 10.0), 0.9,
                    ((4, 0, 2, 2), (7, 0, 3, 3)), (0.65, 0.35)),
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
    return image


def box_for_3d(target: tuple[float, float, float], pitch: float, area: tuple[float, float, float],
               ground: float) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """The box (min corner, size; m) particles fill about the camera's target, for a camera ``pitch`` degrees down:
    from the ground up ``area[2]``, across ``area[0]``, and far enough south that a particle high up, which the
    picture shows further down, still fills the bottom of the picture."""
    w, d, h = area
    back = h / max(0.2, math.tan(math.radians(pitch)))
    return (target[0] - w / 2, target[1] - d / 2 - back, ground), (w, d + back, h)


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
in vec2 in_corner; in vec4 in_seed; in vec2 in_var;
out vec2 v_uv; out float v_alpha;
float hash(float n) { return fract(sin(n) * 43758.5453); }
void main() {
    float t = u_time, phase = in_seed.w, sp = in_var.y;
    vec3 w = in_seed.xyz * u_box_size;  // its place in the endless repeating pattern
    float alpha = 1.0, flip = 1.0, bob = 0.0;
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
        bob = 0.35 * sin(t * 2.3 * sp + phase * 6.2832);  // after the wrap: a leaf never jumps floor to top
        alpha = smoothstep(0.0, 0.12, age) * (1.0 - smoothstep(0.82, 1.0, age));
        flip = sin(t * 5.0 * sp + phase * 6.2832) < 0.0 ? -1.0 : 1.0;
    }
    vec3 p = u_box_min + mod(w - u_box_min, u_box_size);
    vec2 edge = min(p.xy - u_box_min.xy, u_box_min.xy + u_box_size.xy - p.xy);
    alpha *= clamp(min(edge.x, edge.y) / 1.5, 0.0, 1.0);  // fade at the box's sides: wrapping never pops in view
    if (u_kind == 2) {  // leaves keep 0.35 m clear of the floor and top, and bob within that
        p.z = u_box_min.z + 0.35 + (p.z - u_box_min.z) * (u_box_size.z - 0.7) / u_box_size.z + bob;
    } else {            // rain and snow fade in at the top (where a fallen one comes back), vanish at the ground
        alpha *= clamp((u_box_min.z + u_box_size.z - p.z) / 1.5, 0.0, 1.0);
    }
    vec4 vr = u_variants[int(in_var.x + 0.5)];
    vec2 size = vr.zw / 32.0;  // the art's 32 px per metre
    vec3 across = u_right * size.x, along = u_up * size.y;
    if (u_kind == 0) {  // a streak lies along its fall
        vec3 fall = vec3(u_wind * sp, -u_fall * sp);
        along = -normalize(fall) * size.y;
    }
    vec3 world = p + across * in_corner.x * flip + along * in_corner.y;
    v_uv = (vr.xy + vec2(in_corner.x + 0.5, 1.0 - in_corner.y) * vr.zw) / u_atlas;
    v_alpha = alpha;
    gl_Position = u_flat == 1 ? u_vp * vec4(world.x * 32.0, (world.y + world.z) * 32.0, 0.0, 1.0)
                              : u_vp * vec4(world, 1.0);
}
"""
FS = """
#version 330
uniform sampler2D u_tex; uniform vec3 u_light; uniform float u_opacity;
in vec2 v_uv; in float v_alpha; out vec4 f_color;
void main() {
    vec4 c = texture(u_tex, v_uv);
    float a = u_opacity * v_alpha;
    if (c.a < 0.5 || a < 0.004) discard;  // binary alpha, like every Mesh picture
    f_color = vec4(c.rgb * u_light, a);
}
"""


class ParticleLayer:
    """A room's particle effects on the GPU: one program, one atlas, one quad, and per effect a buffer of seeds and a
    draw call. ``update`` advances its clock; ``draw_3d`` / ``draw_2d`` draw every enabled effect; ``release`` frees
    every GPU object (room change, window close)."""

    def __init__(self, ctx: Any, effects: tuple[ParticleEffect, ...], *, gl: Any) -> None:
        self.ctx, self.effects, self.time = ctx, effects, 0.0
        self.enabled = [e.enabled for e in effects]
        self.depth_test = True  # False only to show what depth testing hides (diagnostics)
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
                "u_gust": effect.gust, "u_life": effect.lifetime, "u_opacity": effect.opacity}

    def visible(self) -> bool:
        return any(on and g is not None for on, g in zip(self.enabled, self.geometries))

    def update(self, delta_time: float) -> None:
        self.time += max(0.0, float(delta_time))

    def set_enabled(self, index: int, on: bool) -> None:
        self.enabled[index] = bool(on)

    def memory_bytes(self) -> int:
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
              flat: bool) -> None:
        prog = self.program
        prog["u_vp"] = vp
        prog["u_time"] = self.time
        prog["u_right"], prog["u_up"], prog["u_flat"] = right, up, 1 if flat else 0
        prog["u_atlas"] = (32.0, 24.0)
        prog["u_light"] = light
        prog["u_tex"] = 0
        self.texture.use(0)
        self.draw_calls = 0
        for effect, on, geometry, uniforms, (box_min, box_size) in zip(self.effects, self.enabled, self.geometries,
                                                                       self.uniforms, boxes):
            if not on or geometry is None:
                continue
            for name, value in uniforms.items():
                prog[name] = value
            prog["u_box_min"], prog["u_box_size"] = box_min, box_size
            geometry.render(prog, instances=effect.count)
            self.draw_calls += 1

    def draw_3d(self, vp: tuple[float, ...], camera: Any, ground: float, light: tuple[float, float, float],
                fbo: Any) -> None:
        """Into an HD-2D frame already drawn (its depth kept): depth-tested, not writing depth, blended."""
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
        boxes = [box_for_3d(target, camera.pitch, e.area, ground) for e in self.effects]
        fbo.depth_mask = False
        try:
            with ctx.enabled(ctx.BLEND):
                if not self.depth_test:
                    ctx.disable(ctx.DEPTH_TEST)
                self._draw(vp, boxes, (s[0], s[1], 0.0), u, light, flat=False)
        finally:
            ctx.enable(ctx.DEPTH_TEST)
            fbo.depth_mask = True

    def draw_2d(self, vp: tuple[float, ...], centre_m: tuple[float, float], view_m: tuple[float, float]) -> None:
        """Over a 2D room's map (the world camera in use): x across, y + z up the map."""
        self.draw_calls = 0
        if not self.visible():
            return
        ctx = self.ctx
        boxes = [box_for_2d(centre_m, view_m, e.area) for e in self.effects]
        with ctx.enabled(ctx.BLEND):
            self._draw(vp, boxes, (1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (1.0, 1.0, 1.0), flat=True)


# --- a 2D room's particles (window.scene_particles); an HD-2D room's belong to its renderer --------------------------

def configure(window: Any, settings: Any) -> None:
    """Called while a room loads, after its HD-2D renderer (if any): a 2D room that asks for particles gets a layer."""
    release(window)
    window.scene_particles_error = None
    raw = settings.get("particles") if isinstance(settings, dict) else None
    if raw is None:
        return
    try:
        effects = parse_particles(raw)
        renderer = getattr(window, "hd2d_renderer", None)
        if renderer is not None:
            renderer.set_particles(effects)
        elif effects and getattr(window, "ctx", None) is not None:
            import engine.optional_arcade as optional_arcade  # noqa: PLC0415

            window.scene_particles = ParticleLayer(window.ctx, effects, gl=optional_arcade.arcade.gl)
    except Exception as exc:  # bad settings, or a driver that can't build them: the room still loads, without them
        window.scene_particles_error = str(exc)
        from engine.logging_tools import get_logger  # noqa: PLC0415

        get_logger(__name__).error("[Mesh][Particles] this room's particles are off: %s", exc)


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
    ctx = window.ctx
    vp = ctx.projection_matrix @ ctx.view_matrix
    camera = getattr(window, "camera", None)
    position = getattr(camera, "position", (window.width / 2, window.height / 2))
    zoom = float(getattr(camera, "zoom", 1.0) or 1.0)
    view = (window.width / zoom / PX_PER_M, window.height / zoom / PX_PER_M)
    layer.draw_2d(tuple(vp), (float(position[0]) / PX_PER_M, float(position[1]) / PX_PER_M), view)
