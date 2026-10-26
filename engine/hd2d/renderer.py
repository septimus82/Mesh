"""The HD-2D scene renderer: depth-tested 3D structures from GLB files and the scene's own 2D sprites as upright,
camera-facing billboards, drawn through the window's own ``arcade.gl`` context (no second engine or window).

The world renders into an off-screen framebuffer with a depth attachment, then is drawn into whatever framebuffer
was active (the screen, or the post-processing target). Structures are batched statically: each instance's parts
are transformed once at load and merged into one vertex and index buffer per texture, so a village costs a few draw
calls. Sprites are batched per texture every frame. Pixel art's binary alpha is alpha-tested, so the depth buffer
alone gives correct occlusion, with no sorting.

Every surface is lit per fragment where it is in the world (``engine.hd2d.lighting``: ambient, the sun, lamps,
shadow maps); a frame is the sun's shadow pass (and, once, the lamps'), then the scene.
"""

from __future__ import annotations

import math
from array import array
from pathlib import Path
from typing import Any, Callable, Iterable

from PIL import Image

from engine.hd2d.glb import Model, load_glb
from engine.hd2d.lighting import LIGHTING_GLSL, Lighting
from engine.hd2d.precipitation import PrecipitationMaps, key_for
from engine.hd2d.settings import PIXELS_PER_METRE, Hd2dSettings
from engine.logging_tools import get_logger

logger = get_logger(__name__)

MESH_VS = """
#version 330
uniform mat4 u_vp; uniform mat4 u_model;
in vec3 in_pos; in vec3 in_nrm; in vec2 in_uv;
out vec3 v_nrm; out vec2 v_uv; out vec3 v_world;
void main() {
    vec4 w = u_model * vec4(in_pos, 1.0);
    v_nrm = mat3(u_model) * in_nrm; v_uv = in_uv; v_world = w.xyz; gl_Position = u_vp * w;
}
"""
MESH_FS = """
#version 330
uniform sampler2D u_tex;
// Cutaway (structures marked "cutaway", in play): not drawn within u_cut_at.w metres of the line from the camera
// (u_cut_eye) to the followed character's chest (u_cut_at.xyz), in front of the character and above u_cut_floor.
uniform int u_cut; uniform vec4 u_cut_at; uniform vec3 u_cut_eye; uniform float u_cut_floor;
in vec3 v_nrm; in vec2 v_uv; in vec3 v_world; out vec4 f_color;
""" + LIGHTING_GLSL + """
void main() {
    if (u_cut == 1 && u_cut_at.w > 0.0 && v_world.z > u_cut_floor) {
        vec3 sight = u_cut_at.xyz - u_cut_eye;
        float reach = length(sight);
        vec3 dir = sight / reach;
        float along = dot(v_world - u_cut_eye, dir);
        if (along < reach - 0.2 && distance(v_world, u_cut_eye + dir * along) < u_cut_at.w) discard;
    }
    vec4 c = texture(u_tex, v_uv);
    f_color = vec4(c.rgb * light_at(v_world, normalize(v_nrm), false), 1.0);
}
"""
SPRITE_VS = """
#version 330
uniform mat4 u_vp;
in vec3 in_pos; in vec2 in_uv; out vec2 v_uv; out vec3 v_world;
void main() { v_uv = in_uv; v_world = in_pos; gl_Position = u_vp * vec4(in_pos, 1.0); }
"""
SPRITE_FS = """
#version 330
uniform sampler2D u_tex; uniform int u_solid;
in vec2 v_uv; in vec3 v_world; out vec4 f_color;
""" + LIGHTING_GLSL + """
void main() {
    vec4 c = texture(u_tex, v_uv);
    if (c.a < 0.5) discard;  // binary alpha: discard, write depth for the rest; no sorting needed
    f_color = u_solid == 1 ? vec4(1.0, 0.0, 0.0, 1.0) : vec4(c.rgb * light_at(v_world, vec3(0.0, -1.0, 0.0), true), 1.0);
}
"""
SHADOW_FS = """
#version 330
in vec2 v_uv; out vec4 f_color;
void main() { float d = length(v_uv - 0.5) * 2.0; if (d > 1.0) discard; f_color = vec4(0.0, 0.0, 0.0, 0.35 * (1.0 - d * d)); }
"""
BLIT_VS = """
#version 330
in vec2 in_pos; out vec2 v_uv;
void main() { v_uv = in_pos * 0.5 + 0.5; gl_Position = vec4(in_pos, 0.0, 1.0); }
"""
BLIT_FS = """
#version 330
uniform sampler2D u_tex; in vec2 v_uv; out vec4 f_color;
void main() { f_color = texture(u_tex, v_uv); }
"""
LINE_VS = """
#version 330
uniform mat4 u_vp; in vec3 in_pos;
void main() { gl_Position = u_vp * vec4(in_pos, 1.0); }
"""
LINE_FS = """
#version 330
uniform vec4 u_colour; out vec4 f_color;
void main() { f_color = u_colour; }
"""
IDENTITY = (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)


# ---------------------------------------------------------------------- small linear algebra (column-major out)
def _perspective(fov_deg: float, aspect: float, near: float, far: float) -> list[list[float]]:
    f = 1.0 / math.tan(math.radians(fov_deg) / 2)
    return [[f / aspect, 0, 0, 0], [0, f, 0, 0], [0, 0, (far + near) / (near - far), 2 * far * near / (near - far)],
            [0, 0, -1, 0]]


def _orthographic(half_h: float, aspect: float, near: float, far: float) -> list[list[float]]:
    half_w = half_h * aspect
    return [[1 / half_w, 0, 0, 0], [0, 1 / half_h, 0, 0], [0, 0, -2 / (far - near), -(far + near) / (far - near)],
            [0, 0, 0, 1]]


def _look_at(eye: tuple[float, float, float], target: tuple[float, float, float]) -> list[list[float]]:
    f = [target[i] - eye[i] for i in range(3)]
    n = math.sqrt(sum(v * v for v in f))
    f = [v / n for v in f]
    s = [f[1] * 1.0 - f[2] * 0.0, f[2] * 0.0 - f[0] * 1.0, 0.0]  # f x up(0,0,1)
    n = math.sqrt(sum(v * v for v in s)) or 1.0
    s = [v / n for v in s]
    u = [s[1] * f[2] - s[2] * f[1], s[2] * f[0] - s[0] * f[2], s[0] * f[1] - s[1] * f[0]]
    m = [[s[0], s[1], s[2], 0.0], [u[0], u[1], u[2], 0.0], [-f[0], -f[1], -f[2], 0.0], [0.0, 0.0, 0.0, 1.0]]
    for r in range(3):
        m[r][3] = -sum(m[r][c] * eye[c] for c in range(3))
    return m


def _mul(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def _column_major(m: list[list[float]]) -> tuple[float, ...]:
    return tuple(float(m[r][c]) for c in range(4) for r in range(4))


def _placement(x: float, y: float, z: float, rotation_deg: float, scale: float) -> list[list[float]]:
    """A structure's model matrix: scale, turn about the vertical axis, move (metres)."""
    c, s = math.cos(math.radians(rotation_deg)), math.sin(math.radians(rotation_deg))
    return [[c * scale, -s * scale, 0.0, x], [s * scale, c * scale, 0.0, y], [0.0, 0.0, scale, z], [0.0, 0.0, 0.0, 1.0]]


CUTAWAY_RADIUS = 1.3  # m: how wide the opening is that cutaway structures leave around the line to the player
CUTAWAY_HEIGHT = 0.9  # m above the player's feet: where that line ends (about the chest)


class Camera:
    """A camera looking down at a point (metres) from ``pitch`` degrees above the horizon. The game's looks north
    (yaw 0); Mesh Studio's editing camera can turn about the vertical axis (yaw, degrees clockwise from north)."""

    def __init__(self, pitch: float, fov: float, distance: float, ortho: bool, yaw: float = 0.0) -> None:
        self.pitch, self.fov, self.distance, self.ortho, self.yaw = pitch, fov, distance, ortho, yaw
        self.target = (0.0, 0.0, 0.0)

    def forward(self) -> tuple[float, float]:
        """The horizontal direction it looks (unit)."""
        return math.sin(math.radians(self.yaw)), math.cos(math.radians(self.yaw))

    def right(self) -> tuple[float, float, float]:
        fx, fy = self.forward()
        return (fy, -fx, 0.0)

    def eye(self) -> tuple[float, float, float]:
        p = math.radians(self.pitch)
        fx, fy = self.forward()
        back = math.cos(p) * self.distance
        return (self.target[0] - fx * back, self.target[1] - fy * back, self.target[2] + math.sin(p) * self.distance)

    def ray(self, ndc_x: float, ndc_y: float, aspect: float) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        """The world ray (origin, unit direction) through a point of the picture (-1 .. 1 across and up)."""
        eye, t = self.eye(), self.target
        f = [t[i] - eye[i] for i in range(3)]
        n = math.sqrt(sum(v * v for v in f)) or 1.0
        f = [v / n for v in f]
        s = [f[1], -f[0], 0.0]  # f x up(0, 0, 1)
        n = math.sqrt(s[0] ** 2 + s[1] ** 2) or 1.0
        s = [s[0] / n, s[1] / n, 0.0]
        u = [s[1] * f[2] - s[2] * f[1], s[2] * f[0] - s[0] * f[2], s[0] * f[1] - s[1] * f[0]]
        half_h = math.tan(math.radians(self.fov) / 2)
        if self.ortho:
            hh, hw = self.distance * half_h, self.distance * half_h * aspect
            origin = tuple(eye[i] + s[i] * ndc_x * hw + u[i] * ndc_y * hh for i in range(3))
            return (origin[0], origin[1], origin[2]), (f[0], f[1], f[2])
        d = [f[i] + s[i] * ndc_x * half_h * aspect + u[i] * ndc_y * half_h for i in range(3)]
        n = math.sqrt(sum(v * v for v in d)) or 1.0
        return eye, (d[0] / n, d[1] / n, d[2] / n)

    def view_projection(self, aspect: float) -> list[list[float]]:
        proj = _orthographic(self.distance * math.tan(math.radians(self.fov) / 2), aspect, 0.1, 500.0) if self.ortho \
            else _perspective(self.fov, aspect, 0.1, 500.0)
        return _mul(proj, _look_at(self.eye(), self.target))


def fit_view(camera: Camera, goal: tuple[float, float, float], floor: float,
             bounds: tuple[float, float, float, float], aspect: float) -> tuple[float, float, float]:
    """``goal`` (the follow camera's target, m) moved so the picture of the floor at height ``floor`` (m) stays inside
    ``bounds`` (m: x0, y0, x1, y1), and centred on them along an axis where they are narrower than the picture.
    Unchanged when the picture reaches the horizon (there is no edge of the floor to keep to)."""
    probe = Camera(camera.pitch, camera.fov, camera.distance, camera.ortho, camera.yaw)
    probe.target = goal
    xs, ys = [], []
    for nx, ny in ((-1.0, -1.0), (1.0, -1.0), (-1.0, 1.0), (1.0, 1.0)):
        origin, d = probe.ray(nx, ny, aspect)
        if d[2] >= -1e-6:
            return goal
        t = (floor - origin[2]) / d[2]
        xs.append(origin[0] + d[0] * t - goal[0])
        ys.append(origin[1] + d[1] * t - goal[1])

    def fit(c: float, lo: float, hi: float, a: float, b: float) -> float:  # a, b: the picture's extent about c
        return (lo + hi - a - b) / 2 if hi - lo <= b - a else min(max(c, lo - a), hi - b)

    x0, y0, x1, y1 = bounds
    return fit(goal[0], x0, x1, min(xs), max(xs)), fit(goal[1], y0, y1, min(ys), max(ys)), goal[2]


class Hd2dRenderer:
    def __init__(self, window: Any, settings: Hd2dSettings, resolve: Callable[[str], Path], *, batched: bool = True,
                 models: dict[str, Model] | None = None, live: Iterable[str] = ()) -> None:
        """``models``: already-read models to reuse (Mesh Studio rebuilding after an edit). ``live``: structure ids
        kept out of the static batches and drawn with a transform that can change every frame (the one being
        edited; ``set_live``)."""
        import engine.optional_arcade as optional_arcade  # noqa: PLC0415  # the engine's one arcade import route

        self.models: dict[str, Model] = dict(models or {})  # read (and validated) first: a bad file fails before GL work
        for structure in settings.structures:
            if structure.model not in self.models:
                self.models[structure.model] = load_glb(resolve(structure.model))
        self.window, self.settings, self.batched = window, settings, batched
        self.arcade = optional_arcade.arcade
        self.ctx = window.ctx
        ctx = self.ctx
        self.mesh_prog = ctx.program(vertex_shader=MESH_VS, fragment_shader=MESH_FS)
        self.sprite_prog = ctx.program(vertex_shader=SPRITE_VS, fragment_shader=SPRITE_FS)
        self.shadow_prog = ctx.program(vertex_shader=SPRITE_VS, fragment_shader=SHADOW_FS)
        self.blit_prog = ctx.program(vertex_shader=BLIT_VS, fragment_shader=BLIT_FS)
        self.line_prog = ctx.program(vertex_shader=LINE_VS, fragment_shader=LINE_FS)
        self._lines: tuple[Any, Any] | None = None  # Mesh Studio's overlay lines: (geometry, reused buffer)
        self.last_vp: list[list[float]] | None = None
        self._buffers: list[Any] = []
        self._textures: list[Any] = []
        self._fbo: Any = None
        self._fbo_parts: list[Any] = []
        self._sprite_textures: dict[Any, Any] = {}
        self._dynamic: tuple[Any, Any, Any] | None = None  # (geometry, vertex buffer, index buffer)
        self.triangles = 0
        self._blit = self._geometry(array("f", [-1, -1, 1, -1, -1, 1, 1, 1]), "2f", ["in_pos"], mode=ctx.TRIANGLE_STRIP)
        cam = settings.camera
        self.camera = Camera(cam.pitch, cam.fov, cam.distance, cam.ortho)
        self._aspect = 16 / 9  # the game picture's, from the last frame drawn with the game's camera
        self._camera_ready = False
        self.draw_calls = 0
        self.static: list[tuple[Any, Any, tuple[float, ...]]] = []  # (geometry, texture, model matrix)
        self._cutaway: set[int] = set()  # ids of the static draws drawn with the cutaway (_build_batches)
        self._parts: dict[tuple[str, int], Any] = {}  # (model, part) -> its geometry in its own space (live drawing)
        self._materials: dict[tuple[str, str], Any] = {}
        self.live: dict[str, tuple[str, tuple[float, ...]]] = {}  # id -> (model, matrix)
        self.particles: Any = None  # the room's environmental particles (engine.scene_particles), if it has any
        self.precipitation = PrecipitationMaps(ctx)  # where they meet the world (Milestone 18B; made when needed)
        self.weather_preview = False  # Mesh Studio's "Preview weather": draw them in its editing view too
        self.water: Any = None  # the room's puddles and ponds on the GPU (engine.water; made when it has any)
        self.water_error: str | None = None  # why they're off in this room, if the GPU refused them
        self.preview: tuple[str, tuple[float, ...]] | None = None  # a model about to be placed (Mesh Studio)
        live_ids = set(live)
        for st in settings.structures:
            if st.id in live_ids:
                self.live[st.id] = (st.model, _column_major(_placement(st.x / PIXELS_PER_METRE, st.y / PIXELS_PER_METRE,
                                                                       st.elevation / PIXELS_PER_METRE, st.rotation, st.scale)))
        self._static_buffers: list[Any] = []
        self._build_structures(skip=live_ids)
        self.ground = self._build_ground(resolve) if settings.ground is not None else None
        self.lighting = Lighting(ctx, self.arcade, settings, *self.world_box())

    def world_box(self) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        """The room's extent in metres (structures and ground, with headroom for characters): what the sun's
        shadow map and the precipitation maps cover. Worked out once (the room's structures as loaded)."""
        if getattr(self, "_world_box", None) is None:
            self._world_box = self._measure_world_box()
        return self._world_box

    def _measure_world_box(self) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        corners: list[tuple[float, float, float]] = []
        for st in self.settings.structures:
            m = _placement(st.x / PIXELS_PER_METRE, st.y / PIXELS_PER_METRE, st.elevation / PIXELS_PER_METRE,
                           st.rotation, st.scale)
            lo, hi = self.models[st.model].bounds()
            for x in (lo[0], hi[0]):
                for y in (lo[1], hi[1]):
                    for z in (lo[2], hi[2]):
                        corners.append((m[0][0] * x + m[0][1] * y + m[0][2] * z + m[0][3],
                                        m[1][0] * x + m[1][1] * y + m[1][2] * z + m[1][3],
                                        m[2][0] * x + m[2][1] * y + m[2][2] * z + m[2][3]))
        g = self.settings.ground
        if g is not None:
            z = g.elevation / PIXELS_PER_METRE
            corners += [(g.lo[0] / PIXELS_PER_METRE, g.lo[1] / PIXELS_PER_METRE, z),
                        (g.hi[0] / PIXELS_PER_METRE, g.hi[1] / PIXELS_PER_METRE, z)]
        if not corners:
            corners = [(0.0, 0.0, 0.0), (1.0, 1.0, 0.0)]
        lo3 = (min(c[0] for c in corners), min(c[1] for c in corners), min(c[2] for c in corners))
        hi3 = (max(c[0] for c in corners), max(c[1] for c in corners), max(c[2] for c in corners) + 2.5)
        return lo3, hi3

    # ------------------------------------------------------------------ resources
    def _buffer(self, data: bytes) -> Any:
        buffer = self.ctx.buffer(data=data)
        self._buffers.append(buffer)
        return buffer

    def _geometry(self, data: array, fmt: str, names: list[str], indices: array | None = None, mode: int | None = None) -> Any:
        ctx = self.ctx
        kwargs: dict[str, Any] = {}
        if indices is not None:
            kwargs.update(index_buffer=self._buffer(indices.tobytes()), index_element_size=4)
        if mode is not None:
            kwargs["mode"] = mode
        return ctx.geometry([self.arcade.gl.BufferDescription(self._buffer(data.tobytes()), fmt, names)], **kwargs)

    def _texture(self, image: Image.Image, *, nearest: bool = True, repeat: bool = False) -> Any:
        ctx = self.ctx
        filt = ctx.NEAREST if nearest else ctx.LINEAR
        texture = ctx.texture(image.size, components=4, data=image.convert("RGBA").tobytes(), filter=(filt, filt))
        texture.wrap_x = texture.wrap_y = ctx.REPEAT if repeat else ctx.CLAMP_TO_EDGE
        self._textures.append(texture)
        return texture

    def _material_texture(self, model: str, part: Any, cache: dict[tuple[str, str], Any]) -> Any:
        key = (model, part.material.name)
        if key not in cache:
            image = part.material.image or Image.new("RGBA", (1, 1), (200, 200, 200, 255))
            cache[key] = self._texture(image, nearest=part.material.nearest, repeat=part.material.repeat)
        return cache[key]

    def _build_structures(self, skip: set[str] | None = None) -> None:
        first = len(self._buffers)
        try:
            self._build_batches(skip)
        finally:  # the buffers made here are the static batch's (set_live_ids frees and remakes them; batched only)
            self._static_buffers = self._buffers[first:] if self.batched else []

    def _build_batches(self, skip: set[str] | None) -> None:
        textures = self._materials
        structures = [st for st in self.settings.structures if st.id not in (skip or set())]
        self._cutaway = set()
        if not self.batched:  # one shared buffer per model part, drawn once per instance with its placement
            shared = self._parts
            for st in structures:
                matrix = _column_major(_placement(st.x / PIXELS_PER_METRE, st.y / PIXELS_PER_METRE,
                                                  st.elevation / PIXELS_PER_METRE, st.rotation, st.scale))
                for i, part in enumerate(self.models[st.model].parts):
                    if (st.model, i) not in shared:
                        shared[(st.model, i)] = self._geometry(part.vertices, "3f 3f 2f", ["in_pos", "in_nrm", "in_uv"],
                                                               part.indices)
                    self.static.append((shared[(st.model, i)], self._material_texture(st.model, part, textures), matrix))
                    if st.cutaway:
                        self._cutaway.add(id(self.static[-1]))
                    self.triangles += len(part.indices) // 3
            return
        merged: dict[tuple[int, bool], tuple[Any, array, array]] = {}  # (texture id, cutaway) -> (texture, vertices, indices)
        for st in structures:
            m = _placement(st.x / PIXELS_PER_METRE, st.y / PIXELS_PER_METRE, st.elevation / PIXELS_PER_METRE,
                           st.rotation, st.scale)
            for part in self.models[st.model].parts:
                texture = self._material_texture(st.model, part, textures)
                _, verts, idx = merged.setdefault((id(texture), st.cutaway), (texture, array("f"), array("I")))
                base = len(verts) // 8
                v = part.vertices
                for i in range(0, len(v), 8):
                    px, py, pz, nx, ny, nz = v[i], v[i + 1], v[i + 2], v[i + 3], v[i + 4], v[i + 5]
                    verts.extend((m[0][0] * px + m[0][1] * py + m[0][2] * pz + m[0][3],
                                  m[1][0] * px + m[1][1] * py + m[1][2] * pz + m[1][3],
                                  m[2][0] * px + m[2][1] * py + m[2][2] * pz + m[2][3],
                                  m[0][0] * nx + m[0][1] * ny, m[1][0] * nx + m[1][1] * ny, m[2][2] * nz,
                                  v[i + 6], v[i + 7]))
                idx.extend(j + base for j in part.indices)
                self.triangles += len(part.indices) // 3
        for (_, cutaway), (texture, verts, idx) in merged.items():
            # normals were rotated (and scaled uniformly): renormalise
            for i in range(0, len(verts), 8):
                length = math.sqrt(verts[i + 3] ** 2 + verts[i + 4] ** 2 + verts[i + 5] ** 2) or 1.0
                verts[i + 3], verts[i + 4], verts[i + 5] = verts[i + 3] / length, verts[i + 4] / length, verts[i + 5] / length
            self.static.append((self._geometry(verts, "3f 3f 2f", ["in_pos", "in_nrm", "in_uv"], idx), texture, IDENTITY))
            if cutaway:
                self._cutaway.add(id(self.static[-1]))

    def _build_ground(self, resolve: Callable[[str], Path]) -> tuple[Any, Any]:
        g = self.settings.ground
        assert g is not None
        if g.texture:
            with Image.open(resolve(g.texture)) as img:
                texture = self._texture(img, repeat=True)
        else:
            texture = self._texture(Image.new("RGBA", (1, 1), (86, 132, 72, 255)), repeat=True)
        x0, y0 = g.lo[0] / PIXELS_PER_METRE, g.lo[1] / PIXELS_PER_METRE
        x1, y1 = g.hi[0] / PIXELS_PER_METRE, g.hi[1] / PIXELS_PER_METRE
        z = g.elevation / PIXELS_PER_METRE
        quad = array("f", [x0, y0, z, 0, 0, 1, x0, y0, x1, y0, z, 0, 0, 1, x1, y0,
                           x1, y1, z, 0, 0, 1, x1, y1, x0, y1, z, 0, 0, 1, x0, y1])
        return self._geometry(quad, "3f 3f 2f", ["in_pos", "in_nrm", "in_uv"], array("I", [0, 1, 2, 0, 2, 3])), texture

    def _target_fbo(self, size: tuple[int, int]) -> Any:
        if self._fbo is not None and tuple(self._fbo.size) == tuple(size):
            return self._fbo
        self._release_fbo()
        ctx = self.ctx
        colour, depth = ctx.texture(size, components=4), ctx.depth_texture(size)
        self._fbo_parts = [colour, depth]
        self._fbo = ctx.framebuffer(color_attachments=[colour], depth_attachment=depth)
        return self._fbo

    def _release_fbo(self) -> None:
        if self._fbo is not None:
            self._fbo.delete()
        for part in self._fbo_parts:
            part.delete()
        self._fbo, self._fbo_parts = None, []

    def gl_objects(self) -> list[Any]:
        """Every GPU object this renderer holds right now (to check that ``release`` freed them all)."""
        light = self.lighting
        objects = (list(self._buffers) + list(self._textures) + list(self._sprite_textures.values()) + list(self._fbo_parts)
                   + [self._fbo] + list(self._dynamic[1:] if self._dynamic else []) + list(self._lines[1:] if self._lines else [])
                   + [self.mesh_prog, self.sprite_prog, self.shadow_prog, self.blit_prog, self.line_prog]
                   + list(light._targets) + [light.caster, light.lamp_caster, light.sprite_caster, light.probe_prog]
                   + (self.particles.gl_objects() if self.particles is not None else [])
                   + self.precipitation.gl_objects() + (self.water.gl_objects() if self.water is not None else []))
        return [o for o in objects if o is not None]

    def release(self) -> None:
        """Free every GPU object this renderer made (scene change, window close)."""
        self._release_fbo()
        if self._dynamic is not None:
            for buffer in self._dynamic[1:]:
                buffer.delete()
            self._dynamic = None
        if self._lines is not None:
            self._lines[1].delete()
            self._lines = None
        for texture in list(self._sprite_textures.values()) + self._textures:
            texture.delete()
        for buffer in self._buffers:
            buffer.delete()
        self._buffers, self._textures, self._sprite_textures, self.static = [], [], {}, []
        self.ground = None
        for program in (self.mesh_prog, self.sprite_prog, self.shadow_prog, self.blit_prog, self.line_prog):
            program.delete()
        self.lighting.release()
        self.set_particles(())
        self.precipitation.release()
        if self.water is not None:
            self.water.release()
            self.water = None

    def set_particles(self, effects: tuple[Any, ...],
                      bounds: tuple[float, float, float, float] | None = None) -> None:
        """The room's environmental particles (engine.scene_particles.ParticleEffect), drawn in its 3D world; none frees
        them. ``bounds``: the room's rectangle (m) they're kept inside; without one, what the room is built of (its
        structures and ground), or nowhere if it has neither."""
        if self.particles is not None:
            self.particles.release()
            self.particles = None
        self.precipitation.retain(set())  # the next frame makes the maps the new effects need
        if effects:
            from engine.scene_particles import ParticleLayer  # noqa: PLC0415

            if bounds is None and (self.settings.structures or self.settings.ground is not None):
                lo, hi = self.world_box()  # no room size given: what it's built of
                bounds = (lo[0], lo[1], hi[0], hi[1])
            self.particles = ParticleLayer(self.ctx, tuple(effects), gl=self.arcade.gl, bounds=bounds)

    def precipitation_maps(self) -> list[Any]:
        """Per particle effect, the precipitation map its fall needs (engine.hd2d.precipitation), made from the
        ground and every structure (dragged ones included; not a model being placed) if it isn't cached; None for one
        that doesn't fall or is switched off, or if the map can't be made (it falls as in Stage 18A)."""
        if self.particles is None:
            return []
        from engine.scene_particles import fall_of  # noqa: PLC0415

        every = [fall_of(e) for e in self.particles.effects]
        self.precipitation.retain({key_for(f) for f in every if f is not None})  # an effect switched off keeps its map
        falls = [f if on else None for f, on in zip(every, self.particles.enabled)]
        if not any(falls):
            return [None] * len(falls)
        lo, hi = self.world_box()
        return [self.precipitation.get(f, self._precipitation_draws, lo, hi) if f is not None else None for f in falls]

    def _precipitation_draws(self) -> list[tuple[Any, Any, tuple[float, ...]]]:
        """What a precipitation map is drawn from (only when one is made): the ground and every structure."""
        return (([(self.ground[0], self.ground[1], IDENTITY)] if self.ground else []) + self.static
                + [d for model, matrix in self.live.values() for d in self._model_draws(model, matrix)])

    # ------------------------------------------------------------------ the scene's sprites
    def _sprites(self) -> list[Any]:
        scene = getattr(self.window, "scene_controller", None)
        out = []
        for sprite in list(getattr(scene, "all_sprites", None) or []):
            if not getattr(sprite, "visible", True) or not getattr(sprite, "mesh_drawn", True):
                continue
            texture = getattr(sprite, "texture", None)
            if texture is None or getattr(texture, "image", None) is None or getattr(sprite, "alpha", 255) == 0:
                continue
            out.append(sprite)
        return out

    @staticmethod
    def elevation_of(sprite: Any) -> float:
        data = getattr(sprite, "mesh_entity_data", None) or {}
        value = data.get("elevation", 0.0)
        return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0

    def _sprite_texture(self, texture: Any) -> Any:
        key = getattr(texture, "hash", None) or id(texture)
        if key not in self._sprite_textures:
            self._sprite_textures[key] = self.ctx.texture(texture.image.size, components=4,
                                                          data=texture.image.convert("RGBA").tobytes(),
                                                          filter=(self.ctx.NEAREST, self.ctx.NEAREST))
        return self._sprite_textures[key]

    @staticmethod
    def _quad(verts: array, idx: array, corners: tuple[float, ...]) -> None:
        base = len(verts) // 5
        verts.extend(corners)
        idx.extend((base, base + 1, base + 2, base + 2, base + 1, base + 3))

    def _sprite_quads(self, sprites: list[Any], shadows: bool,
                      right: tuple[float, float, float] = (1.0, 0.0, 0.0)) -> tuple[array, array, list[tuple[Any, int, int]]]:
        """This frame's sprite geometry: ground shadows first (texture None), then upright billboards at each
        sprite's feet (its bottom edge on the map), facing the camera and stretched by 1 / cos(pitch) so they keep
        their drawn proportions; grouped by texture as (texture, first index, index count) ranges."""
        verts, idx, ranges = array("f"), array("I"), []
        if shadows:
            for sprite in sprites:
                x, y = sprite.center_x / PIXELS_PER_METRE, sprite.bottom / PIXELS_PER_METRE
                z = self.elevation_of(sprite) / PIXELS_PER_METRE + 0.01
                r = max(0.3, abs(sprite.width) / PIXELS_PER_METRE * 0.45)
                self._quad(verts, idx, (x - r, y - r * 0.6, z, 0, 0, x + r, y - r * 0.6, z, 1, 0,
                                        x - r, y + r * 0.6, z, 0, 1, x + r, y + r * 0.6, z, 1, 1))
            ranges.append((None, 0, len(idx)))
        stretch = 1.0 / max(0.5, math.cos(math.radians(self.camera.pitch)))
        groups: dict[int, tuple[Any, list[Any]]] = {}
        for sprite in sprites:
            tex = self._sprite_texture(sprite.texture)
            groups.setdefault(id(tex), (tex, []))[1].append(sprite)
        for tex, members in groups.values():
            first = len(idx)
            for sprite in members:
                half = abs(sprite.width) / PIXELS_PER_METRE / 2
                h = abs(sprite.height) / PIXELS_PER_METRE * stretch
                x, y = sprite.center_x / PIXELS_PER_METRE, sprite.bottom / PIXELS_PER_METRE
                z = self.elevation_of(sprite) / PIXELS_PER_METRE
                u0, u1 = (1.0, 0.0) if getattr(sprite, "scale_x", 1.0) < 0 else (0.0, 1.0)
                rx, ry = right[0] * half, right[1] * half  # across the picture, facing the camera
                self._quad(verts, idx, (x - rx, y - ry, z, u0, 1.0, x + rx, y + ry, z, u1, 1.0,
                                        x - rx, y - ry, z + h, u0, 0.0, x + rx, y + ry, z + h, u1, 0.0))
            ranges.append((tex, first, len(idx) - first))
        return verts, idx, ranges

    def _upload_dynamic(self, verts: array, idx: array) -> Any:
        """One reused vertex + index buffer for the moving sprites, grown (doubled) only when a frame needs more,
        so a frame allocates nothing on the GPU."""
        need_v, need_i = len(verts) * 4, len(idx) * 4
        if self._dynamic is None or self._dynamic[1].size < need_v or self._dynamic[2].size < need_i:
            if self._dynamic is not None:
                for buffer in self._dynamic[1:]:
                    buffer.delete()
            vbo = self.ctx.buffer(reserve=20 * max(256, len(verts) // 5 * 2))  # whole vertices (5 floats)
            ibo = self.ctx.buffer(reserve=4 * max(384, len(idx) * 2))
            geometry = self.ctx.geometry([self.arcade.gl.BufferDescription(vbo, "3f 2f", ["in_pos", "in_uv"])],
                                         index_buffer=ibo, index_element_size=4)
            self._dynamic = (geometry, vbo, ibo)
        self._dynamic[1].write(verts.tobytes())
        self._dynamic[2].write(idx.tobytes())
        return self._dynamic[0]

    # ------------------------------------------------------------------ structures being edited (Mesh Studio)
    def _model_draws(self, model: str, matrix: tuple[float, ...]) -> list[tuple[Any, Any, tuple[float, ...]]]:
        out = []
        for i, part in enumerate(self.models[model].parts):
            if (model, i) not in self._parts:
                self._parts[(model, i)] = self._geometry(part.vertices, "3f 3f 2f", ["in_pos", "in_nrm", "in_uv"],
                                                         part.indices)
            out.append((self._parts[(model, i)], self._material_texture(model, part, self._materials), matrix))
        return out

    def live_draws(self) -> list[tuple[Any, Any, tuple[float, ...]]]:
        draws = [d for model, matrix in self.live.values() for d in self._model_draws(model, matrix)]
        if self.preview is not None:
            draws += self._model_draws(*self.preview)
        return draws

    def set_live_ids(self, ids: Iterable[str]) -> None:
        """Make these structures live (drawn on their own, movable) and batch the rest again. Mesh Studio calls it
        when a drag starts; the next load of the room (the edit committed) builds plain static batches."""
        ids = set(ids)
        if ids == set(self.live) or not self.batched:
            return
        for buffer in self._static_buffers:
            buffer.delete()
        gone = {id(b) for b in self._static_buffers}
        self._buffers = [b for b in self._buffers if id(b) not in gone]
        self.static, self.triangles = [], 0
        self.live = {st.id: (st.model, _column_major(_placement(st.x / PIXELS_PER_METRE, st.y / PIXELS_PER_METRE,
                                                                st.elevation / PIXELS_PER_METRE, st.rotation, st.scale)))
                     for st in self.settings.structures if st.id in ids}
        self._build_structures(skip=ids)
        self.lighting.invalidate()
        self.precipitation.invalidate()

    def set_live(self, structure_id: str, x: float, y: float, elevation: float, rotation: float, scale: float) -> None:
        """Move a live structure (px, degrees) for this and later frames; its shadows follow."""
        model = self.live[structure_id][0]
        self.live[structure_id] = (model, _column_major(_placement(x / PIXELS_PER_METRE, y / PIXELS_PER_METRE,
                                                                   elevation / PIXELS_PER_METRE, rotation, scale)))
        self.lighting.invalidate()
        self.precipitation.invalidate()  # rain falls on it where it is now

    def set_preview(self, model: str | None, x: float = 0.0, y: float = 0.0, elevation: float = 0.0,
                    rotation: float = 0.0, scale: float = 1.0) -> None:
        """Show ``model`` (already read into ``models``) where it would be placed, or nothing (None)."""
        self.preview = None if model is None else (model, _column_major(_placement(
            x / PIXELS_PER_METRE, y / PIXELS_PER_METRE, elevation / PIXELS_PER_METRE, rotation, scale)))
        self.lighting.invalidate()

    # ------------------------------------------------------------------ overlay lines (Mesh Studio)
    def draw_lines(self, vp: tuple[float, ...], points: list[tuple[float, float, float]],
                   colour: tuple[float, float, float, float], *, through: bool = False) -> None:
        """Line segments (pairs of world points, metres) in one colour, depth-tested unless ``through``."""
        if not points:
            return
        ctx = self.ctx
        data = array("f", [c for p in points for c in p])
        if self._lines is None or self._lines[1].size < len(data) * 4:
            if self._lines is not None:
                self._lines[1].delete()
            buffer = ctx.buffer(reserve=12 * max(256, len(points) * 2))
            self._lines = (ctx.geometry([self.arcade.gl.BufferDescription(buffer, "3f", ["in_pos"])], mode=ctx.LINES),
                           buffer)
        self._lines[1].write(data.tobytes())
        self.line_prog["u_vp"] = vp
        self.line_prog["u_colour"] = colour
        if through:
            ctx.disable(ctx.DEPTH_TEST)
        with ctx.enabled(ctx.BLEND):  # faint lines are see-through
            self._lines[0].render(self.line_prog, vertices=len(points))
        if through:
            ctx.enable(ctx.DEPTH_TEST)

    # ------------------------------------------------------------------ per frame
    def followed(self) -> Any | None:
        tag = self.settings.camera.follow
        for sprite in self._sprites():
            if getattr(sprite, "mesh_tag", None) == tag:
                return sprite
        return None

    def _bind_cutaway(self, program: Any, game_camera: Camera | None) -> None:
        """The cutaway's line of sight: the game's camera to its followed character (none in Mesh Studio, or when no
        structure is marked cutaway)."""
        sprite = self.followed() if game_camera is not None and self._cutaway else None
        if sprite is None or game_camera is None:
            program["u_cut_at"] = (0.0, 0.0, 0.0, 0.0)
            return
        floor = self.elevation_of(sprite) / PIXELS_PER_METRE
        program["u_cut_at"] = (sprite.center_x / PIXELS_PER_METRE, sprite.bottom / PIXELS_PER_METRE,
                               floor + CUTAWAY_HEIGHT, CUTAWAY_RADIUS)
        program["u_cut_eye"] = game_camera.eye()
        program["u_cut_floor"] = floor + 0.05

    def update(self, delta_time: float) -> None:
        if self.particles is not None:
            self.particles.update(delta_time)
        sprite = self.followed()
        if sprite is None:
            return
        cam = self.settings.camera
        goal = (sprite.center_x / PIXELS_PER_METRE, sprite.bottom / PIXELS_PER_METRE,
                self.elevation_of(sprite) / PIXELS_PER_METRE + cam.height)
        if cam.bounds is not None:
            ground = self.settings.ground
            floor = ground.elevation / PIXELS_PER_METRE if ground is not None else goal[2] - cam.height
            x0, y0, x1, y1 = (v / PIXELS_PER_METRE for v in cam.bounds)
            goal = fit_view(self.camera, goal, floor, (x0, y0, x1, y1), self._aspect)
        if not self._camera_ready:
            self.camera.target, self._camera_ready = goal, True
            return
        k = 1.0 - math.exp(-8.0 * max(0.0, delta_time))  # smooth follow, frame-rate independent
        self.camera.target = tuple(t + (g - t) * k for t, g in zip(self.camera.target, goal))

    def draw(self, *, solid: Any | None = None, read: bool = False, camera: Camera | None = None,
             viewport: tuple[int, int, int, int] | None = None, overlay: Callable[[tuple[float, ...]], None] | None = None) -> Any:
        """Draw the world into the active framebuffer. ``solid``: draw only that sprite, flat red, against the
        world's depth (for measuring what of it is visible); ``read``: return the rendered pixels (RGB bytes).
        Mesh Studio's editing view passes its own ``camera``, the ``viewport`` (x, y, w, h) of its canvas, and an
        ``overlay`` drawn in the world with its depth (selection boxes, the grid); the game's camera is untouched."""
        ctx = self.ctx
        previous = ctx.active_framebuffer
        size = (int(viewport[2]), int(viewport[3])) if viewport else (int(previous.size[0]), int(previous.size[1]))
        fbo = self._target_fbo(size)
        if camera is None and not self._camera_ready:
            self.update(0.0)
        cam = camera or self.camera
        if camera is None:
            self._aspect = size[0] / max(1, size[1])
        self.last_vp = cam.view_projection(size[0] / max(1, size[1]))
        vp = _column_major(self.last_vp)
        self.draw_calls = 0
        ctx.disable(ctx.CULL_FACE)
        lighting = self.lighting
        # This frame's characters first: the sun's shadow pass needs them before the scene is drawn. With real
        # shadows on, no painted blob under them (their shadows fall from the sun); off, Stage 2's soft blob.
        sprites = [solid] if solid is not None else self._sprites()
        verts, idx, ranges = self._sprite_quads(sprites, shadows=solid is None and not lighting.enabled, right=cam.right())
        geometry_sprites = self._upload_dynamic(verts, idx) if sprites else None
        live = self.live_draws()
        if solid is None:
            lighting.render_shadows(self.static + live, geometry_sprites, ranges)  # the ground receives, never casts
        weather = self.particles is not None and solid is None and (camera is None or self.weather_preview)
        maps = self.precipitation_maps() if weather else []  # before the frame's target is in use: cached, mostly
        fbo.use()
        fbo.clear(color=(*(round(c * 255) for c in self.settings.sky), 255), depth=1.0)
        ctx.enable(ctx.DEPTH_TEST)
        mp = self.mesh_prog
        mp["u_vp"] = vp
        mp["u_tex"] = 0
        lighting.bind(mp)
        statics = ([(self.ground[0], self.ground[1], IDENTITY)] if self.ground else []) + self.static + live
        self._bind_cutaway(mp, cam if camera is None else None)
        for draw in statics:
            geometry, texture, matrix = draw
            mp["u_cut"] = 1 if id(draw) in self._cutaway else 0
            mp["u_model"] = matrix
            texture.use(0)
            geometry.render(mp)
            self.draw_calls += 1
        if solid is not None:  # keep the depth, clear the colour
            fbo.depth_mask = False
            fbo.clear(color=(0, 0, 0, 255))
            fbo.depth_mask = True
        sp = self.sprite_prog
        sp["u_vp"] = vp
        sp["u_tex"] = 0
        sp["u_solid"] = 1 if solid is not None else 0
        lighting.bind(sp)
        self.shadow_prog["u_vp"] = vp
        if geometry_sprites is not None:
            geometry = geometry_sprites
            for texture, first, count in ranges:
                if texture is None:  # soft shadows: blended, no depth writes
                    with ctx.enabled(ctx.BLEND):
                        fbo.depth_mask = False
                        geometry.render(self.shadow_prog, first=first, vertices=count)
                        fbo.depth_mask = True
                else:
                    texture.use(0)
                    geometry.render(sp, first=first, vertices=count)
                self.draw_calls += 1
        self._draw_water(vp, cam, fbo, weather, maps, solid)
        if weather:  # the game's view (or Studio's, previewing): falling in its world, landing on it
            ground = self.settings.ground.elevation / PIXELS_PER_METRE if self.settings.ground is not None else 0.0
            st = self.settings
            light = tuple(min(1.2, st.ambient * a + st.sun_intensity * 0.55 * max(0.0, st.sun[2]) * c)
                          for a, c in zip(st.ambient_color, st.sun_color))
            self.particles.draw_3d(vp, cam, ground, light, fbo, maps)
            self.draw_calls += self.particles.draw_calls
        elif self.particles is not None:
            self.particles.draw_calls = 0  # not drawn in this view (Studio, not previewing)
        if overlay is not None and solid is None:
            overlay(vp)
        ctx.disable(ctx.DEPTH_TEST)
        pixels = fbo.read(components=3) if read else None
        previous.use()
        self._fbo_parts[0].use(0)
        with ctx.enabled_only():
            if viewport:
                full = ctx.viewport
                ctx.viewport = viewport
                self._blit.render(self.blit_prog)
                ctx.viewport = full
            else:
                self._blit.render(self.blit_prog)
        return pixels

    def _draw_water(self, vp: tuple[float, ...], cam: Camera, fbo: Any, weather: bool, maps: list[Any],
                    solid: Any) -> None:
        """The room's puddles and ponds (engine.water), after its structures and characters: rippled by its rain when
        that is drawn (and not kept off them by something above: the rain's precipitation map)."""
        from engine import water as water_mod  # noqa: PLC0415

        bodies = water_mod.bodies_of(self.window)
        if not bodies or solid is not None or self.water_error is not None:
            if self.water is not None:
                self.water.draw_calls = 0
            return
        try:
            self._draw_water_now(water_mod, bodies, vp, cam, fbo, weather, maps)
        except Exception as exc:  # the driver refused it: no water in this room (its next load tries again)
            self.water_error = f"water: {exc}"
            logger.error("[Mesh][Water] %s (water is off in this room)", self.water_error)
            if self.water is not None:
                self.water.release()
                self.water = None
            fbo.use(force=True)

    def _draw_water_now(self, water_mod: Any, bodies: list[Any], vp: tuple[float, ...], cam: Camera, fbo: Any,
                        weather: bool, maps: list[Any]) -> None:
        if self.water is None:
            self.water = water_mod.WaterLayer(self.ctx, gl=self.arcade.gl)
        self.water.set_bodies(bodies)
        if self.last_vp is not None and not self.water.in_view(self.last_vp):
            self.water.draw_calls = 0
            return
        rain, shelter = 0.0, None
        if weather and self.particles is not None:
            rain = water_mod.rain_rate(self.particles.effects, self.particles.enabled)
            shelter = next((m for e, m in zip(self.particles.effects, maps) if e.preset == "rain" and m is not None), None)
        st = self.settings
        light = tuple(min(1.2, st.ambient * a + st.sun_intensity * 0.55 * max(0.0, st.sun[2]) * c)
                      for a, c in zip(st.ambient_color, st.sun_color))
        self.water.draw_3d(vp, cam.eye(), fbo, time=float(getattr(self.window, "water_time", 0.0)),
                           steps=list(getattr(self.window, "water_steps", None) or []), rain=rain, shelter=shelter,
                           light=light, sky=tuple(st.sky))
        self.draw_calls += self.water.draw_calls

    def visible_pixels(self, sprite: Any) -> int:
        """How many of ``sprite``'s pixels pass the depth test against the world (for tests and diagnostics)."""
        data = self.draw(solid=sprite, read=True)
        return sum(1 for i in range(0, len(data), 3) if data[i] > 200 and data[i + 1] < 60)

    def stats(self) -> dict[str, Any]:
        """Draw calls last frame, triangles and GPU memory this renderer holds (static buffers, textures, target)."""
        texture_bytes = sum(t.width * t.height * 4 for t in self._textures + list(self._sprite_textures.values()))
        target_bytes = sum(p.width * p.height * 4 for p in self._fbo_parts)
        buffer_bytes = sum(b.size for b in self._buffers + list(self._dynamic[1:] if self._dynamic else []))
        return {"draw_calls": self.draw_calls, "static_draws": len(self.static) + (1 if self.ground else 0),
                "triangles": self.triangles, "buffer_bytes": buffer_bytes,
                "texture_bytes": texture_bytes, "target_bytes": target_bytes, "batched": self.batched,
                "shadows": self.lighting.enabled, "shadow_draws": self.lighting.shadow_draws,
                "shadow_map_bytes": self.lighting.memory_bytes(), "lamps": len(self.lighting.lamps),
                "shadow_lamps": sum(1 for slot in self.lighting.lamp_slots if slot >= 0),
                "particles": sum(e.count for e, on in zip(self.particles.effects, self.particles.enabled) if on)
                if self.particles is not None else 0,
                "particle_bytes": self.particles.memory_bytes() if self.particles is not None else 0,
                "precipitation_maps": len(self.precipitation.maps),
                "precipitation_bytes": self.precipitation.memory_bytes(),
                "precipitation_builds": self.precipitation.builds,
                "precipitation_error": self.precipitation.error,
                "water_surfaces": self.water.count if self.water is not None else 0,
                "water_bytes": self.water.memory_bytes() if self.water is not None else 0,
                "water_error": self.water_error}
