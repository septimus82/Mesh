"""The HD-2D scene renderer: depth-tested 3D structures from GLB files and the scene's own 2D sprites as upright,
camera-facing billboards, drawn through the window's own ``arcade.gl`` context (no second engine or window).

The world renders into an off-screen framebuffer with a depth attachment, then is drawn into whatever framebuffer
was active (the screen, or the post-processing target). Structures are batched statically: each instance's parts
are transformed once at load and merged into one vertex and index buffer per texture, so a village costs a few draw
calls. Sprites are batched per texture every frame. Pixel art's binary alpha is alpha-tested, so the depth buffer
alone gives correct occlusion, with no sorting.
"""

from __future__ import annotations

import math
from array import array
from pathlib import Path
from typing import Any, Callable

from PIL import Image

from engine.hd2d.glb import Model, load_glb
from engine.hd2d.settings import PIXELS_PER_METRE, Hd2dSettings
from engine.logging_tools import get_logger

logger = get_logger(__name__)

MESH_VS = """
#version 330
uniform mat4 u_vp; uniform mat4 u_model;
in vec3 in_pos; in vec3 in_nrm; in vec2 in_uv;
out vec3 v_nrm; out vec2 v_uv;
void main() { v_nrm = mat3(u_model) * in_nrm; v_uv = in_uv; gl_Position = u_vp * u_model * vec4(in_pos, 1.0); }
"""
MESH_FS = """
#version 330
uniform sampler2D u_tex; uniform vec3 u_sun; uniform float u_ambient;
in vec3 v_nrm; in vec2 v_uv; out vec4 f_color;
void main() {
    vec4 c = texture(u_tex, v_uv);
    float light = u_ambient + (1.0 - u_ambient) * max(dot(normalize(v_nrm), u_sun), 0.0);
    f_color = vec4(c.rgb * light, 1.0);
}
"""
SPRITE_VS = """
#version 330
uniform mat4 u_vp;
in vec3 in_pos; in vec2 in_uv; out vec2 v_uv;
void main() { v_uv = in_uv; gl_Position = u_vp * vec4(in_pos, 1.0); }
"""
SPRITE_FS = """
#version 330
uniform sampler2D u_tex; uniform float u_light; uniform int u_solid;
in vec2 v_uv; out vec4 f_color;
void main() {
    vec4 c = texture(u_tex, v_uv);
    if (c.a < 0.5) discard;  // binary alpha: discard, write depth for the rest; no sorting needed
    f_color = u_solid == 1 ? vec4(1.0, 0.0, 0.0, 1.0) : vec4(c.rgb * u_light, 1.0);
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


class Camera:
    """A fixed-angle camera looking north and down at a followed point (metres)."""

    def __init__(self, pitch: float, fov: float, distance: float, ortho: bool) -> None:
        self.pitch, self.fov, self.distance, self.ortho = pitch, fov, distance, ortho
        self.target = (0.0, 0.0, 0.0)

    def eye(self) -> tuple[float, float, float]:
        p = math.radians(self.pitch)
        return (self.target[0], self.target[1] - math.cos(p) * self.distance, self.target[2] + math.sin(p) * self.distance)

    def view_projection(self, aspect: float) -> list[list[float]]:
        proj = _orthographic(self.distance * math.tan(math.radians(self.fov) / 2), aspect, 0.1, 500.0) if self.ortho \
            else _perspective(self.fov, aspect, 0.1, 500.0)
        return _mul(proj, _look_at(self.eye(), self.target))


class Hd2dRenderer:
    def __init__(self, window: Any, settings: Hd2dSettings, resolve: Callable[[str], Path], *, batched: bool = True) -> None:
        import engine.optional_arcade as optional_arcade  # noqa: PLC0415  # the engine's one arcade import route

        self.models: dict[str, Model] = {}  # read (and validated) first: a bad file fails before any GL work
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
        self._camera_ready = False
        self.draw_calls = 0
        self.static: list[tuple[Any, Any, tuple[float, ...]]] = []  # (geometry, texture, model matrix)
        self._build_structures()
        self.ground = self._build_ground(resolve) if settings.ground is not None else None

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

    def _build_structures(self) -> None:
        textures: dict[tuple[str, str], Any] = {}
        if not self.batched:  # one shared buffer per model part, drawn once per instance with its placement
            shared: dict[tuple[str, int], Any] = {}
            for st in self.settings.structures:
                matrix = _column_major(_placement(st.x / PIXELS_PER_METRE, st.y / PIXELS_PER_METRE,
                                                  st.elevation / PIXELS_PER_METRE, st.rotation, st.scale))
                for i, part in enumerate(self.models[st.model].parts):
                    if (st.model, i) not in shared:
                        shared[(st.model, i)] = self._geometry(part.vertices, "3f 3f 2f", ["in_pos", "in_nrm", "in_uv"],
                                                               part.indices)
                    self.static.append((shared[(st.model, i)], self._material_texture(st.model, part, textures), matrix))
                    self.triangles += len(part.indices) // 3
            return
        merged: dict[int, tuple[Any, array, array]] = {}  # texture id -> (texture, vertices, indices)
        for st in self.settings.structures:
            m = _placement(st.x / PIXELS_PER_METRE, st.y / PIXELS_PER_METRE, st.elevation / PIXELS_PER_METRE,
                           st.rotation, st.scale)
            for part in self.models[st.model].parts:
                texture = self._material_texture(st.model, part, textures)
                _, verts, idx = merged.setdefault(id(texture), (texture, array("f"), array("I")))
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
        for texture, verts, idx in merged.values():
            # normals were rotated (and scaled uniformly): renormalise
            for i in range(0, len(verts), 8):
                length = math.sqrt(verts[i + 3] ** 2 + verts[i + 4] ** 2 + verts[i + 5] ** 2) or 1.0
                verts[i + 3], verts[i + 4], verts[i + 5] = verts[i + 3] / length, verts[i + 4] / length, verts[i + 5] / length
            self.static.append((self._geometry(verts, "3f 3f 2f", ["in_pos", "in_nrm", "in_uv"], idx), texture, IDENTITY))

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

    def release(self) -> None:
        """Free every GPU object this renderer made (scene change, window close)."""
        self._release_fbo()
        if self._dynamic is not None:
            for buffer in self._dynamic[1:]:
                buffer.delete()
            self._dynamic = None
        for texture in list(self._sprite_textures.values()) + self._textures:
            texture.delete()
        for buffer in self._buffers:
            buffer.delete()
        self._buffers, self._textures, self._sprite_textures, self.static = [], [], {}, []
        self.ground = None
        for program in (self.mesh_prog, self.sprite_prog, self.shadow_prog, self.blit_prog):
            program.delete()

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

    def _sprite_quads(self, sprites: list[Any], shadows: bool) -> tuple[array, array, list[tuple[Any, int, int]]]:
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
                self._quad(verts, idx, (x - half, y, z, u0, 1.0, x + half, y, z, u1, 1.0,
                                        x - half, y, z + h, u0, 0.0, x + half, y, z + h, u1, 0.0))
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

    # ------------------------------------------------------------------ per frame
    def followed(self) -> Any | None:
        tag = self.settings.camera.follow
        for sprite in self._sprites():
            if getattr(sprite, "mesh_tag", None) == tag:
                return sprite
        return None

    def update(self, delta_time: float) -> None:
        sprite = self.followed()
        if sprite is None:
            return
        cam = self.settings.camera
        goal = (sprite.center_x / PIXELS_PER_METRE, sprite.bottom / PIXELS_PER_METRE,
                self.elevation_of(sprite) / PIXELS_PER_METRE + cam.height)
        if not self._camera_ready:
            self.camera.target, self._camera_ready = goal, True
            return
        k = 1.0 - math.exp(-8.0 * max(0.0, delta_time))  # smooth follow, frame-rate independent
        self.camera.target = tuple(t + (g - t) * k for t, g in zip(self.camera.target, goal))

    def draw(self, *, solid: Any | None = None, read: bool = False) -> Any:
        """Draw the world into the active framebuffer. ``solid``: draw only that sprite, flat red, against the
        world's depth (for measuring what of it is visible); ``read``: return the rendered pixels (RGB bytes)."""
        ctx = self.ctx
        previous = ctx.active_framebuffer
        size = (int(previous.size[0]), int(previous.size[1]))
        fbo = self._target_fbo(size)
        if not self._camera_ready:
            self.update(0.0)
        vp = _column_major(self.camera.view_projection(size[0] / max(1, size[1])))
        self.draw_calls = 0
        fbo.use()
        fbo.clear(color=(118, 160, 214, 255), depth=1.0)
        ctx.enable(ctx.DEPTH_TEST)
        ctx.disable(ctx.CULL_FACE)
        mp = self.mesh_prog
        mp["u_vp"] = vp
        sun = self.settings.sun
        length = math.sqrt(sum(v * v for v in sun))
        mp["u_sun"] = tuple(v / length for v in sun)
        mp["u_ambient"] = self.settings.ambient
        statics = ([(self.ground[0], self.ground[1], IDENTITY)] if self.ground else []) + self.static
        for geometry, texture, matrix in statics:
            mp["u_model"] = matrix
            texture.use(0)
            geometry.render(mp)
            self.draw_calls += 1
        if solid is not None:  # keep the depth, clear the colour
            fbo.depth_mask = False
            fbo.clear(color=(0, 0, 0, 255))
            fbo.depth_mask = True
        sprites = [solid] if solid is not None else self._sprites()
        sp = self.sprite_prog
        sp["u_vp"] = vp
        sp["u_light"] = self.settings.ambient + (1 - self.settings.ambient) * 0.75
        sp["u_solid"] = 1 if solid is not None else 0
        self.shadow_prog["u_vp"] = vp
        if sprites:
            verts, idx, ranges = self._sprite_quads(sprites, shadows=solid is None)
            geometry = self._upload_dynamic(verts, idx)
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
        ctx.disable(ctx.DEPTH_TEST)
        pixels = fbo.read(components=3) if read else None
        previous.use()
        self._fbo_parts[0].use(0)
        with ctx.enabled_only():
            self._blit.render(self.blit_prog)
        return pixels

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
                "texture_bytes": texture_bytes, "target_bytes": target_bytes, "batched": self.batched}
