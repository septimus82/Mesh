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
"""

from __future__ import annotations

import math
from array import array
from dataclasses import dataclass, replace
from typing import Any

PX_PER_M = 32.0
MAX_STEPS = 8  # footstep ripples alive at once (the oldest gives way)
STEP_RIPPLE_S = 1.0  # how long a footstep's ring lasts
_KEYS = {"preset", "width", "height", "colour", "opacity", "shape", "waves", "rain_ripples", "walkable", "step_sound",
         "reflection"}
SHAPES = ("ellipse", "rect")


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


PRESETS: dict[str, Water] = {
    "puddle": Water("puddle", 64.0, 40.0, (0.42, 0.50, 0.58), 0.62, "ellipse", 0.15, 0.85, True, True, ""),
    "pond": Water("pond", 224.0, 144.0, (0.16, 0.36, 0.42), 0.84, "ellipse", 0.6, 0.55, True, True, ""),
}


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


def parse_water(raw: Any) -> Water:
    """A ``WaterSurface`` config checked and completed from its preset."""
    if not isinstance(raw, dict):
        raise WaterError("water settings must be an object like {\"preset\": \"pond\"}")
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
    return replace(
        base, width=_number(raw.get("width", base.width), "water width", 8, 8192),
        height=_number(raw.get("height", base.height), "water height", 8, 8192),
        colour=_hex(raw["colour"], "water colour") if "colour" in raw else base.colour,
        opacity=_number(raw.get("opacity", base.opacity), "water opacity", 0.05, 1.0), shape=shape,
        waves=_number(raw.get("waves", base.waves), "water waves", 0.0, 1.0),
        reflection=_number(raw.get("reflection", base.reflection), "water reflection", 0.0, 1.0),
        rain_ripples=bool(raw.get("rain_ripples", base.rain_ripples)), walkable=bool(raw.get("walkable", base.walkable)),
        step_sound=sound.strip())


def inside(water: Water, centre: tuple[float, float], point: tuple[float, float], margin: float = 0.0) -> bool:
    """Whether ``point`` (px) is on the water's surface (``margin`` px in from its edge)."""
    hw, hh = water.width / 2 - margin, water.height / 2 - margin
    if hw <= 0 or hh <= 0:
        return False
    dx, dy = (point[0] - centre[0]) / hw, (point[1] - centre[1]) / hh
    return dx * dx + dy * dy <= 1.0 if water.shape == "ellipse" else abs(dx) <= 1.0 and abs(dy) <= 1.0


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
    layer = getattr(window, "scene_water", None)
    if layer is not None:
        layer.release()
    window.scene_water = None


def advance(window: Any, delta_time: float) -> None:
    if getattr(window, "water_bodies", None):
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
out vec3 v_world; out vec2 v_local; flat out vec4 v_rect; flat out vec4 v_info; flat out vec4 v_colour; flat out vec4 v_look;
void main() {
    // in_rect: centre x, y (m), half width, half height (m); in_info: level z (m), shape (0 ellipse, 1 rect),
    // kind (0 puddle, 1 pond), rain ripples (0/1); in_look: waves, reflection, seed, unused
    vec3 world = vec3(in_rect.xy + in_corner * in_rect.zw, in_info.x);
    v_world = world; v_local = in_corner; v_rect = in_rect; v_info = in_info; v_colour = in_colour; v_look = in_look;
    gl_Position = u_flat == 1 ? u_vp * vec4(world.x * 32.0, (world.y + world.z) * 32.0, 0.0, 1.0)
                              : u_vp * vec4(world, 1.0);
}
"""
FS = """
#version 330
uniform float u_time; uniform int u_flat; uniform mat4 u_vp; uniform vec3 u_eye; uniform vec3 u_sky; uniform vec3 u_light;
uniform float u_rain; uniform int u_shelter; uniform sampler2D u_precip; uniform mat4 u_precip_vp;
uniform vec4 u_steps[8]; uniform int u_steps_n;
uniform int u_reflect; uniform sampler2D u_scene; uniform sampler2D u_scene_depth; uniform vec2 u_screen;
in vec3 v_world; in vec2 v_local; flat in vec4 v_rect; flat in vec4 v_info; flat in vec4 v_colour; flat in vec4 v_look;
out vec4 f_color;
float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
// rings on the surface: a ring of radius r (m) about c, as a narrow band, fading with age 0..1
float ring(vec2 q, vec2 c, float r, float age) {
    float d = abs(length(q - c) - r);
    return (1.0 - smoothstep(0.0, 0.045, d)) * (1.0 - age);
}
void main() {
    // the pixel grid: everything is worked out at the centre of this fragment's texel (32 per metre)
    vec2 q = (floor(v_world.xy * 32.0) + 0.5) / 32.0;
    vec2 local = (q - v_rect.xy) / v_rect.zw;  // -1..1 across the surface
    float shape = v_info.y, kind = v_info.z;
    float inside = shape < 0.5 ? 1.0 - length(local)
                               : 1.0 - max(abs(local.x), abs(local.y)) * 0.96 - 0.04 * length(local);
    if (inside < 0.0) discard;
    float edge_m = inside * min(v_rect.z, v_rect.w);  // roughly how far in from the edge (m)
    float t = u_time, seed = v_look.z;
    // gentle waves: their slope bends the surface's normal
    float w = v_look.x * (kind > 0.5 ? 0.06 : 0.025);
    vec2 slope = w * vec2(cos(q.x * 5.1 + q.y * 1.7 + t * 1.3 + seed) * 5.1 + cos(q.x * -2.3 + q.y * 4.6 + t * 0.9) * -2.3,
                          cos(q.x * 5.1 + q.y * 1.7 + t * 1.3 + seed) * 1.7 + cos(q.x * -2.3 + q.y * 4.6 + t * 0.9) * 4.6);
    float rings = 0.0, splash = 0.0;
    // rain: in cells of 0.5 m each starts rings at hashed places and moments, as often as the rain is heavy
    bool rained = u_rain > 0.0 && v_info.w > 0.5;
    if (rained && u_shelter == 1) {  // something above (a roof, the deck): the rain doesn't reach this water
        vec3 m = (u_precip_vp * vec4(q, v_world.z + 0.05, 1.0)).xyz * 0.5 + 0.5;
        if (m.x >= 0.0 && m.x <= 1.0 && m.y >= 0.0 && m.y <= 1.0 && texture(u_precip, m.xy).r < m.z - 0.002) rained = false;
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
    // footsteps: a ring from each, and a few splash pixels at first
    for (int i = 0; i < u_steps_n; i++) {
        float age = (t - u_steps[i].z) / 1.0;
        if (age < 0.0 || age > 1.0) continue;
        rings += 1.4 * ring(q, u_steps[i].xy, 0.06 + age * 0.55, age);
        vec2 off = q - u_steps[i].xy;
        if (age < 0.25 && length(off) < 0.12 + age * 0.4 && hash(floor(q * 32.0) + floor(t * 12.0)) > 0.86) splash += 1.0;
    }
    vec3 n = normalize(vec3(-slope + rings * 0.35 * normalize(local + 0.001), 1.0));
    // the water's own colour: a pond darker towards its middle, lighter at its rim
    vec3 col = v_colour.rgb;
    float deep = kind > 0.5 ? smoothstep(0.1, 1.6, edge_m) : 0.0;
    col *= mix(1.0, 0.62, deep);
    float rim = (kind > 0.5 ? 1.0 - smoothstep(0.0, 0.16, edge_m) : 1.0 - smoothstep(0.0, 0.06, edge_m));
    // what it mirrors: the sky, or (HD-2D) what's on screen along the mirrored view ray
    vec3 view = u_flat == 1 ? vec3(0.0, 0.35, -0.94) : normalize(vec3(q, v_world.z) - u_eye);
    vec3 r = reflect(view, n);
    vec3 refl = u_sky;
    if (u_reflect == 1) {
        for (int s = 1; s <= 10; s++) {
            vec3 p = vec3(q, v_world.z) + r * (0.18 * float(s * s) * 0.5);
            vec4 c = u_vp * vec4(p, 1.0);
            vec3 ndc = c.xyz / c.w;
            vec2 uv = ndc.xy * 0.5 + 0.5;
            if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) break;
            float scene_d = texture(u_scene_depth, uv).r;
            if (scene_d < ndc.z * 0.5 + 0.5 - 0.000002) {  // something on screen is in front of the ray here
                refl = texture(u_scene, (floor(uv * u_screen) + 0.5) / u_screen).rgb;
                break;
            }
        }
    }
    float facing = clamp(-view.z, 0.0, 1.0);
    float fresnel = v_look.y * mix(0.85, 0.35, facing);
    vec3 lit = mix(col * u_light, refl, fresnel);
    lit += vec3(0.85, 0.92, 1.0) * clamp(rings, 0.0, 1.0) * 0.35;  // rings catch the light
    lit = mix(lit, vec3(0.88, 0.94, 1.0) * u_light, rim * 0.35 + clamp(splash, 0.0, 1.0) * 0.8);
    float alpha = clamp(v_colour.a * smoothstep(0.0, 0.04, inside * 2.0) + clamp(rings, 0.0, 1.0) * 0.2 + splash * 0.6, 0.0, 1.0);
    // a few flat shades: pixel art, not a gradient
    lit = floor(lit * 24.0 + 0.5) / 24.0;
    f_color = vec4(lit, alpha);
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
            rows.append((x, y, w.width / PX_PER_M / 2, w.height / PX_PER_M / 2,
                         z + 0.012, 0.0 if w.shape == "ellipse" else 1.0, 1.0 if w.preset == "pond" else 0.0,
                         1.0 if w.rain_ripples else 0.0, *w.colour, w.opacity, w.waves, w.reflection, 1.7 * i, 0.0))
        key = tuple(rows)
        if key == self._key:
            return
        self._key, self.count = key, len(rows)
        data = array("f", [v for row in rows for v in row]).tobytes() if rows else b""
        if self.instances is not None and self.instances.size >= max(1, len(data)):
            if data:
                self.instances.write(data)
            return
        self._free_geometry()
        if not rows:
            return
        self.instances = self.ctx.buffer(data=data)
        gl = self.gl
        self.geometry = self.ctx.geometry(
            [gl.BufferDescription(self.quad, "2f", ["in_corner"]),
             gl.BufferDescription(self.instances, "4f 4f 4f 4f", ["in_rect", "in_info", "in_colour", "in_look"],
                                  instanced=True)],
            mode=self.ctx.TRIANGLE_STRIP)

    def _free_geometry(self) -> None:
        if self.geometry is not None:
            self.geometry.flush()
        if self.instances is not None:
            self.instances.delete()
        self.geometry = self.instances = None

    def _copy_of(self, fbo: Any) -> tuple[Any, Any, Any]:
        """The frame so far, copied (colour and depth): what reflections look into."""
        size = tuple(fbo.size)
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
        self.ctx.copy_framebuffer(fbo, self.copy[0], depth=True)
        return self.copy

    def _free_copy(self) -> None:
        if self.copy is not None:
            for obj in self.copy:
                obj.delete()
        self.copy = None

    def _uniforms(self, time: float, steps: list[tuple[float, float, float]], rain: float, shelter: Any,
                  light: tuple[float, float, float], sky: tuple[float, float, float]) -> None:
        prog = self.program
        prog["u_time"] = time
        live = [s for s in steps if 0.0 <= time - s[2] <= STEP_RIPPLE_S][-8:]
        prog["u_steps"] = tuple(v for s in live for v in (s[0], s[1], s[2], 1.0)) + (0.0,) * (4 * (8 - len(live)))
        prog["u_steps_n"] = len(live)
        prog["u_rain"] = rain
        prog["u_light"], prog["u_sky"] = light, sky
        shelter = shelter if self.shelter else None
        prog["u_shelter"] = 1 if shelter is not None else 0
        prog["u_precip"], prog["u_scene"], prog["u_scene_depth"] = 1, 2, 3
        if shelter is not None:
            shelter.depth.use(1)
            prog["u_precip_vp"] = shelter.vp

    def draw_3d(self, vp: tuple[float, ...], eye: tuple[float, float, float], fbo: Any, *, time: float,
                steps: list[tuple[float, float, float]], rain: float, shelter: Any,
                light: tuple[float, float, float], sky: tuple[float, float, float], reflect: bool = True) -> None:
        """Into an HD-2D frame already drawn (structures and characters, their depth kept)."""
        self.draw_calls = 0
        if self.geometry is None or not self.count:
            return
        ctx, prog = self.ctx, self.program
        if reflect:
            _frame, colour, depth = self._copy_of(fbo)
            colour.use(2)
            depth.use(3)
            prog["u_screen"] = tuple(float(v) for v in fbo.size)
        prog["u_reflect"] = 1 if reflect else 0
        prog["u_vp"], prog["u_eye"], prog["u_flat"] = vp, eye, 0
        self._uniforms(time, steps, rain, shelter, light, sky)
        fbo.use(force=True)  # copy_framebuffer left the copy bound for drawing, unknown to arcade's own record
        fbo.depth_mask = False
        try:
            with ctx.enabled(ctx.BLEND):
                if self.depth_test:
                    ctx.enable(ctx.DEPTH_TEST)
                else:
                    ctx.disable(ctx.DEPTH_TEST)
                self.geometry.render(prog, instances=self.count)
        finally:
            ctx.enable(ctx.DEPTH_TEST)
            fbo.depth_mask = True
        self.draw_calls = 1

    def draw_2d(self, vp: tuple[float, ...], *, time: float, steps: list[tuple[float, float, float]], rain: float,
                sky: tuple[float, float, float]) -> None:
        """On a 2D room's map, under its characters (the world camera in use)."""
        self.draw_calls = 0
        if self.geometry is None or not self.count:
            return
        prog = self.program
        prog["u_vp"], prog["u_eye"], prog["u_flat"], prog["u_reflect"] = vp, (0.0, 0.0, 0.0), 1, 0
        prog["u_screen"] = (1.0, 1.0)
        self._uniforms(time, steps, rain, None, (1.0, 1.0, 1.0), sky)
        with self.ctx.enabled(self.ctx.BLEND):
            self.geometry.render(prog, instances=self.count)
        self.draw_calls = 1

    def gl_objects(self) -> list[Any]:
        return [o for o in (self.program, self.quad, self.instances, *(self.copy or ())) if o is not None]

    def memory_bytes(self) -> int:
        size = (self.instances.size if self.instances is not None else 0) + (self.quad.size if self.quad else 0)
        if self.copy is not None:
            w, h = self.copy[1].size
            size += w * h * 8
        return int(size)

    def release(self) -> None:
        """Free every GPU object (also of a partly made layer); a second call does nothing."""
        self._free_geometry()
        self._free_copy()
        for obj in (self.quad, self.program):
            if obj is not None:
                obj.delete()
        self.quad = self.program = None
        self._key, self.count = None, 0


def bodies_of(window: Any) -> list[Body]:
    """The room's water surfaces shown now: all of them, but those an object's "Show when" flags hide (a water
    object has no picture, so its sprite is never ``visible``: that isn't the test)."""
    bodies = list(getattr(window, "water_bodies", None) or [])
    get_flag = getattr(window, "get_flag", None)
    if not bodies or not callable(get_flag):
        return bodies
    from engine.scene_entity_gating import runtime_entity_passes_flag_gates  # noqa: PLC0415

    return [b for b in bodies if runtime_entity_passes_flag_gates(b.entity, get_flag=get_flag)]


def draw_2d(window: Any) -> None:
    """A 2D room's water, after its ground and before its characters (``engine.scene_controller_parts.rendering``)."""
    bodies = bodies_of(window)
    if not bodies or getattr(window, "hd2d_renderer", None) is not None or getattr(window, "ctx", None) is None:
        return
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
