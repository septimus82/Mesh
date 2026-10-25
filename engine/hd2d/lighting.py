"""HD-2D lighting and shadows (Milestone 16 Stage 4): ambient light, a sun (or moon) and coloured lamps, with
shadow maps, for structures, the ground and character billboards alike. 2D rooms never use this; their lighting
is the 2D compositor's (engine.lighting), unchanged.

Every surface is lit per fragment at its own world position (metres), so a character is lit where it stands, at
its height, and its head and feet can differ (half under a bridge, half in the sun). Shadows are depth maps:

- the sun's: one orthographic depth map fitted to the room (``settings.hd2d.shadow_resolution``, 2048 by default),
  re-drawn every frame so moving characters cast shadows too (it holds the batched structures and the billboards);
- each shadow-casting lamp's (at most ``MAX_SHADOW_LIGHTS``): six 90-degree faces of distance-to-the-lamp, packed
  in one atlas (``POINT_FACE`` px a face; a row per such lamp). Lamps and structures don't move, so these are drawn once, when the room's
  first frame is drawn, and only again when asked (``invalidate``). Characters don't cast lamp shadows.

Depth maps are read with a plain ``sampler2D`` and compared in the shader (arcade 3.3 can't bind
``sampler2DShadow``), filtered over 1, 3 x 3 or 5 x 5 texels by the room's shadow softness (sharp / soft / softer,
the 2D setting). Acne is kept off with a small depth bias plus an offset of the receiving point along its normal
(towards the sun or lamp for billboards, which have none); the offset is a few centimetres, so shadows stay
attached at the foot of a wall.
"""

from __future__ import annotations

import math
from array import array
from typing import Any

from engine.hd2d.settings import MAX_LIGHTS, MAX_SHADOW_LIGHTS, PIXELS_PER_METRE, Hd2dSettings

POINT_FACE = 512  # px: one face of a lamp's shadow map
POINT_NEAR = 0.05  # m
SOFTNESS_PCF = {"sharp": 0, "soft": 1, "softer": 2}  # filter radius in texels (1, 3 x 3, 5 x 5 samples)

LIGHTING_GLSL = """
uniform vec3 u_ambient;          // ambient colour x strength
uniform vec3 u_sun_dir;          // towards the sun (unit)
uniform vec3 u_sun_color;        // colour x intensity x (1 - ambient)
uniform int u_shadows;           // 1: shadow maps are on
uniform float u_shadow_strength; // 0 .. 1 (the room's shadow strength)
uniform int u_pcf;               // filter radius: 0 sharp, 1 soft, 2 softer
uniform sampler2D u_sun_map;
uniform mat4 u_sun_vp;
uniform float u_sun_texel;
uniform int u_light_count;
uniform vec4 u_light_pos[8];     // xyz (m), w: radius (m)
uniform vec4 u_light_col[8];     // rgb x intensity, w: shadow slot (-1: none)
uniform sampler2D u_point_maps;  // per shadow slot a row of 6 faces: distance / radius
uniform mat4 u_face_vp[12];
uniform float u_point_rows;      // rows in the lamps' atlas (one per shadow-casting lamp)
uniform vec3 u_terms;            // weights of ambient, sun, lamps (1, 1, 1; the light probe isolates one)

float sun_visibility(vec3 p) {
    if (u_shadows == 0) return 1.0;
    vec4 c = u_sun_vp * vec4(p, 1.0);
    vec3 s = c.xyz / c.w * 0.5 + 0.5;
    if (s.x <= 0.0 || s.x >= 1.0 || s.y <= 0.0 || s.y >= 1.0 || s.z >= 1.0) return 1.0;
    float lit = 0.0, n = 0.0;
    for (int dx = -2; dx <= 2; dx++) {
        for (int dy = -2; dy <= 2; dy++) {
            if (abs(dx) > u_pcf || abs(dy) > u_pcf) continue;
            lit += (s.z - 0.0012 <= texture(u_sun_map, s.xy + vec2(dx, dy) * u_sun_texel).r) ? 1.0 : 0.0;
            n += 1.0;
        }
    }
    return mix(1.0, lit / n, u_shadow_strength);
}

float lamp_visibility(int slot, vec3 p, vec3 lp, float radius) {
    if (u_shadows == 0 || slot < 0) return 1.0;
    vec3 d = p - lp;
    vec3 a = abs(d);
    int face = (a.x >= a.y && a.x >= a.z) ? (d.x > 0.0 ? 0 : 1) : ((a.y >= a.z) ? (d.y > 0.0 ? 2 : 3) : (d.z > 0.0 ? 4 : 5));
    vec4 c = u_face_vp[slot * 6 + face] * vec4(p, 1.0);
    vec2 texel = 1.0 / vec2(textureSize(u_point_maps, 0));
    vec2 face_texel = texel * vec2(6.0, u_point_rows);
    vec2 uv = clamp(c.xy / c.w * 0.5 + 0.5, face_texel * 1.5, 1.0 - face_texel * 1.5);
    vec2 base = (vec2(float(face), float(slot)) + uv) / vec2(6.0, u_point_rows);
    float dist = length(d) / radius;
    float lit = 0.0, n = 0.0;
    for (int dx = -1; dx <= 1; dx++) {
        for (int dy = -1; dy <= 1; dy++) {
            if (u_pcf == 0 && (dx != 0 || dy != 0)) continue;
            lit += (dist - 0.006 <= texture(u_point_maps, base + vec2(dx, dy) * texel).r) ? 1.0 : 0.0;
            n += 1.0;
        }
    }
    return mix(1.0, lit / n, u_shadow_strength);
}

// The light arriving at p (world metres) on a surface facing n; billboard: a character sprite (no real normal:
// it takes a fixed share of each light, so it reads the same from every side, and is offset towards the light).
vec3 light_at(vec3 p, vec3 n, bool billboard) {
    vec3 c = u_ambient * u_terms.x;
    float sun = billboard ? 0.75 : max(dot(n, u_sun_dir), 0.0);
    if (sun > 0.0) {
        vec3 q = billboard ? p + u_sun_dir * 0.15 : p + n * 0.03;
        c += u_sun_color * sun * sun_visibility(q) * u_terms.y;
    }
    for (int i = 0; i < 8; i++) {
        if (i >= u_light_count) break;
        vec3 lp = u_light_pos[i].xyz;
        float r = u_light_pos[i].w;
        vec3 d = lp - p;
        float dist = length(d);
        if (dist >= r) continue;
        vec3 l = d / max(dist, 1e-4);
        float facing = billboard ? 0.85 : max(dot(n, l), 0.0);
        if (facing <= 0.0) continue;
        float fall = 1.0 - dist / r;
        vec3 q = billboard ? p + l * 0.15 : p + n * 0.03;
        c += u_light_col[i].rgb * fall * fall * facing * lamp_visibility(int(u_light_col[i].w), q, lp, r) * u_terms.z;
    }
    return c;
}
"""

CASTER_VS = """
#version 330
uniform mat4 u_vp; uniform mat4 u_model;
in vec3 in_pos; out vec3 v_world;
void main() { vec4 w = u_model * vec4(in_pos, 1.0); v_world = w.xyz; gl_Position = u_vp * w; }
"""
CASTER_FS = """
#version 330
void main() { }
"""
LAMP_CASTER_FS = """
#version 330
uniform vec4 u_lamp;  // xyz, radius
in vec3 v_world;
void main() { gl_FragDepth = clamp(length(v_world - u_lamp.xyz) / u_lamp.w, 0.0, 1.0); }
"""
SPRITE_CASTER_VS = """
#version 330
uniform mat4 u_vp;
in vec3 in_pos; in vec2 in_uv; out vec2 v_uv;
void main() { v_uv = in_uv; gl_Position = u_vp * vec4(in_pos, 1.0); }
"""
SPRITE_CASTER_FS = """
#version 330
uniform sampler2D u_tex;
in vec2 v_uv;
void main() { if (texture(u_tex, v_uv).a < 0.5) discard; }
"""
PROBE_VS = """
#version 330
uniform int u_count;
in vec3 in_pos; in vec3 in_nrm; in float in_billboard;
out vec3 v_pos; out vec3 v_nrm; flat out int v_billboard;
void main() {
    v_pos = in_pos; v_nrm = in_nrm; v_billboard = int(in_billboard);
    gl_Position = vec4((float(gl_VertexID) + 0.5) / float(u_count) * 2.0 - 1.0, 0.0, 0.0, 1.0);
    gl_PointSize = 1.0;
}
"""
PROBE_FS = """
#version 330
in vec3 v_pos; in vec3 v_nrm; flat in int v_billboard;
out vec4 f_color;
""" + LIGHTING_GLSL + """
void main() { f_color = vec4(light_at(v_pos, normalize(v_nrm), v_billboard == 1), 1.0); }
"""


def _mul(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def _column_major(m: list[list[float]]) -> tuple[float, ...]:
    return tuple(float(m[r][c]) for c in range(4) for r in range(4))


def _view(eye: tuple[float, float, float], forward: tuple[float, float, float],
          up: tuple[float, float, float]) -> list[list[float]]:
    f = _unit(forward)
    s = _unit((f[1] * up[2] - f[2] * up[1], f[2] * up[0] - f[0] * up[2], f[0] * up[1] - f[1] * up[0]))
    u = (s[1] * f[2] - s[2] * f[1], s[2] * f[0] - s[0] * f[2], s[0] * f[1] - s[1] * f[0])
    rows = [list(s), list(u), [-f[0], -f[1], -f[2]]]
    return [r + [-sum(r[k] * eye[k] for k in range(3))] for r in rows] + [[0.0, 0.0, 0.0, 1.0]]


def _unit(v: tuple[float, ...]) -> tuple[float, float, float]:
    n = math.sqrt(sum(c * c for c in v)) or 1.0
    return (v[0] / n, v[1] / n, v[2] / n)


def _ortho(x0: float, x1: float, y0: float, y1: float, near: float, far: float) -> list[list[float]]:
    return [[2 / (x1 - x0), 0, 0, -(x1 + x0) / (x1 - x0)], [0, 2 / (y1 - y0), 0, -(y1 + y0) / (y1 - y0)],
            [0, 0, -2 / (far - near), -(far + near) / (far - near)], [0, 0, 0, 1]]


def _perspective90(near: float, far: float) -> list[list[float]]:
    return [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, (far + near) / (near - far), 2 * far * near / (near - far)], [0, 0, -1, 0]]


# The six faces: the direction each looks and its up; a point lies in the face of its largest axis (the shader's
# face choice), which is exactly what each 90-degree frustum sees.
FACES = (((1, 0, 0), (0, 0, 1)), ((-1, 0, 0), (0, 0, 1)), ((0, 1, 0), (0, 0, 1)), ((0, -1, 0), (0, 0, 1)),
         ((0, 0, 1), (0, 1, 0)), ((0, 0, -1), (0, 1, 0)))


def sun_matrix(direction: tuple[float, float, float], lo: tuple[float, float, float],
               hi: tuple[float, float, float]) -> list[list[float]]:
    """An orthographic view-projection along the sun that holds the whole box (lo, hi) in metres."""
    d = _unit(direction)
    centre = tuple((lo[k] + hi[k]) / 2 for k in range(3))
    reach = math.sqrt(sum((hi[k] - lo[k]) ** 2 for k in range(3))) / 2 + 1.0
    eye = (centre[0] + d[0] * reach, centre[1] + d[1] * reach, centre[2] + d[2] * reach)
    up = (0.0, 1.0, 0.0) if abs(d[2]) > 0.99 else (0.0, 0.0, 1.0)
    view = _view(eye, (-d[0], -d[1], -d[2]), up)
    corners = [(x, y, z) for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]
    pts = [[sum(view[r][k] * c[k] for k in range(3)) + view[r][3] for r in range(3)] for c in corners]
    x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
    y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
    near, far = -max(p[2] for p in pts) - 0.5, -min(p[2] for p in pts) + 0.5
    return _mul(_ortho(x0, x1, y0, y1, max(0.01, near), far), view)


def face_matrices(lamp: tuple[float, float, float], radius: float) -> list[list[list[float]]]:
    proj = _perspective90(POINT_NEAR, radius)
    return [_mul(proj, _view(lamp, f, u)) for f, u in FACES]


class Lighting:
    """The room's lights and shadow maps on the renderer's GL context: uniforms for the lit programs, the
    shadow passes, a light probe, and its share of the renderer's statistics and clean-up."""

    def __init__(self, ctx: Any, arcade: Any, settings: Hd2dSettings, world_lo: tuple[float, float, float],
                 world_hi: tuple[float, float, float]) -> None:
        self.ctx, self.arcade, self.settings = ctx, arcade, settings
        self.enabled = settings.shadows  # shadows on/off (lights always)
        self.pcf = SOFTNESS_PCF.get(settings.shadow_softness, 0)
        self.sun = _unit(settings.sun)
        self.sun_vp = sun_matrix(self.sun, world_lo, world_hi)
        self.lamps = [lamp for lamp in settings.lights][:MAX_LIGHTS]
        self.lamp_slots: list[int] = []
        self.face_vps: list[list[list[float]]] = []
        slot = 0
        for lamp in self.lamps:
            if lamp.shadows and slot < MAX_SHADOW_LIGHTS:
                self.lamp_slots.append(slot)
                self.face_vps.extend(face_matrices(self._lamp_pos(lamp), lamp.radius / PIXELS_PER_METRE))
                slot += 1
            else:
                self.lamp_slots.append(-1)
        self.point_rows = slot  # the lamps' atlas: one row of six faces per shadow-casting lamp
        self._targets: list[Any] = []  # the shadow maps, made when shadows are first drawn (never, if they're off)
        self.sun_map: Any = None
        self.sun_fbo: Any = None
        self.point_map: Any = None
        self.point_fbo: Any = None
        self.caster = ctx.program(vertex_shader=CASTER_VS, fragment_shader=CASTER_FS)
        self.lamp_caster = ctx.program(vertex_shader=CASTER_VS, fragment_shader=LAMP_CASTER_FS)
        self.sprite_caster = ctx.program(vertex_shader=SPRITE_CASTER_VS, fragment_shader=SPRITE_CASTER_FS)
        self.probe_prog = ctx.program(vertex_shader=PROBE_VS, fragment_shader=PROBE_FS)
        self._lamp_maps_ready = False
        self.shadow_draws = 0  # last frame's draw calls into shadow maps
        self.lamp_map_renders = 0  # how many times the lamps' maps were drawn

    @staticmethod
    def _lamp_pos(lamp: Any) -> tuple[float, float, float]:
        return (lamp.x / PIXELS_PER_METRE, lamp.y / PIXELS_PER_METRE, lamp.elevation / PIXELS_PER_METRE)

    def _depth_target(self, size: tuple[int, int]) -> tuple[Any, Any]:
        ctx = self.ctx
        depth = ctx.depth_texture(size)
        depth.compare_func = None  # read as depth, compared in the shader
        depth.filter = (ctx.NEAREST, ctx.NEAREST)
        # arcade's framebuffers need a colour attachment: the smallest there is (1 byte a texel, never written)
        colour = ctx.texture(size, components=1, dtype="u1")
        fbo = ctx.framebuffer(color_attachments=[colour], depth_attachment=depth)
        self._targets += [fbo, depth, colour]
        return depth, fbo

    def _maps(self) -> None:
        if self.sun_map is None:
            size = self.settings.shadow_resolution
            self.sun_map, self.sun_fbo = self._depth_target((size, size))
            if self.point_rows:
                self.point_map, self.point_fbo = self._depth_target((6 * POINT_FACE, self.point_rows * POINT_FACE))

    def invalidate(self) -> None:
        """Draw the lamps' shadow maps again before the next frame (after structures or lamps change)."""
        self._lamp_maps_ready = False

    # ------------------------------------------------------------------ uniforms for a lit program
    def bind(self, program: Any, *, terms: tuple[float, float, float] = (1.0, 1.0, 1.0)) -> None:
        s = self.settings
        program["u_ambient"] = tuple(c * s.ambient for c in s.ambient_color)
        program["u_sun_dir"] = self.sun
        program["u_sun_color"] = tuple(c * s.sun_intensity * (1 - s.ambient) for c in s.sun_color)
        program["u_shadows"] = 1 if self.enabled else 0
        program["u_shadow_strength"] = s.shadow_strength
        program["u_pcf"] = self.pcf
        program["u_sun_map"] = 1
        program["u_point_maps"] = 2
        program["u_sun_vp"] = _column_major(self.sun_vp)
        program["u_sun_texel"] = 1.0 / s.shadow_resolution
        program["u_light_count"] = len(self.lamps)
        pos, col = [0.0] * 32, [0.0] * 32
        for i, lamp in enumerate(self.lamps):
            pos[i * 4: i * 4 + 4] = [*self._lamp_pos(lamp), lamp.radius / PIXELS_PER_METRE]
            col[i * 4: i * 4 + 4] = [*(c * lamp.intensity for c in lamp.color), float(self.lamp_slots[i])]
        program["u_light_pos"] = tuple(pos)
        program["u_light_col"] = tuple(col)
        faces = [_column_major(m) for m in self.face_vps] + [_column_major([[1.0 if r == c else 0.0 for c in range(4)]
                                                                          for r in range(4)])] * (12 - len(self.face_vps))
        program["u_face_vp"] = tuple(v for m in faces for v in m)
        program["u_terms"] = terms
        program["u_point_rows"] = float(max(1, self.point_rows))
        if self.enabled:
            self._maps()
            self.sun_map.use(1)
            if self.point_map is not None:
                self.point_map.use(2)

    # ------------------------------------------------------------------ shadow passes
    def render_shadows(self, statics: list[tuple[Any, Any, tuple[float, ...]]], sprites: Any | None,
                       sprite_ranges: list[tuple[Any, int, int]]) -> None:
        """The sun's map (structures and billboards: every frame) and, once, the lamps' maps (structures)."""
        self.shadow_draws = 0
        if not self.enabled:
            return
        ctx = self.ctx
        previous = ctx.active_framebuffer
        try:
            self._render_shadows(statics, sprites, sprite_ranges)
        finally:
            previous.use()  # whatever was being drawn into before

    def _render_shadows(self, statics: list[tuple[Any, Any, tuple[float, ...]]], sprites: Any | None,
                        sprite_ranges: list[tuple[Any, int, int]]) -> None:
        ctx = self.ctx
        self._maps()
        ctx.enable(ctx.DEPTH_TEST)
        if not self._lamp_maps_ready and self.point_fbo is not None:
            self.point_fbo.use()
            self.point_fbo.clear(depth=1.0)
            prog = self.lamp_caster
            for i, lamp in enumerate(self.lamps):
                slot = self.lamp_slots[i]
                if slot < 0:
                    continue
                prog["u_lamp"] = (*self._lamp_pos(lamp), lamp.radius / PIXELS_PER_METRE)
                for face in range(6):
                    self.point_fbo.viewport = (face * POINT_FACE, slot * POINT_FACE, POINT_FACE, POINT_FACE)
                    prog["u_vp"] = _column_major(self.face_vps[slot * 6 + face])
                    for geometry, _texture, matrix in statics:
                        prog["u_model"] = matrix
                        geometry.render(prog)
                        self.shadow_draws += 1
            self.point_fbo.viewport = (0, 0, *self.point_map.size)
            self._lamp_maps_ready = True
            self.lamp_map_renders += 1
        self.sun_fbo.use()
        self.sun_fbo.clear(depth=1.0)
        vp = _column_major(self.sun_vp)
        self.caster["u_vp"] = vp
        for geometry, _texture, matrix in statics:
            self.caster["u_model"] = matrix
            geometry.render(self.caster)
            self.shadow_draws += 1
        if sprites is not None:
            self.sprite_caster["u_vp"] = vp
            self.sprite_caster["u_tex"] = 0
            for texture, first, count in sprite_ranges:
                if texture is None:
                    continue
                texture.use(0)
                sprites.render(self.sprite_caster, first=first, vertices=count)
                self.shadow_draws += 1

    # ------------------------------------------------------------------ measuring
    def probe(self, points: list[tuple[float, float, float, float, float, float, bool]],
              terms: tuple[float, float, float] = (1.0, 1.0, 1.0)) -> list[tuple[float, float, float]]:
        """The light arriving at each (x, y, z, nx, ny, nz, billboard) in metres, exactly as the scene's shaders
        compute it (same functions, same shadow maps: draw a frame first), one pixel per point of a float target."""
        ctx = self.ctx
        data = array("f")
        for x, y, z, nx, ny, nz, billboard in points:
            data.extend((x, y, z, nx, ny, nz, 1.0 if billboard else 0.0))
        target = ctx.texture((len(points), 1), components=4, dtype="f4")
        fbo = ctx.framebuffer(color_attachments=[target])
        buffer = ctx.buffer(data=data.tobytes())
        geometry = ctx.geometry([self.arcade.gl.BufferDescription(buffer, "3f 3f 1f", ["in_pos", "in_nrm", "in_billboard"])],
                                mode=ctx.POINTS)
        previous = ctx.active_framebuffer
        try:
            fbo.use()
            fbo.clear(color=(0, 0, 0, 0))
            self.bind(self.probe_prog, terms=terms)
            self.probe_prog["u_count"] = len(points)
            with ctx.enabled_only():
                geometry.render(self.probe_prog)
            raw = array("f")
            raw.frombytes(fbo.read(components=4, dtype="f4"))
            return [(raw[i * 4], raw[i * 4 + 1], raw[i * 4 + 2]) for i in range(len(points))]
        finally:
            previous.use()
            for obj in (fbo, target, buffer):
                obj.delete()

    def memory_bytes(self) -> int:
        """The shadow maps' GPU memory: 4 bytes of depth and 1 of (unused) colour a texel."""
        return sum(m.width * m.height * 5 for m in (self.sun_map, self.point_map) if m is not None)

    def release(self) -> None:
        for obj in self._targets + [self.caster, self.lamp_caster, self.sprite_caster, self.probe_prog]:
            obj.delete()
        self._targets, self.sun_map, self.point_map, self.sun_fbo, self.point_fbo = [], None, None, None, None
