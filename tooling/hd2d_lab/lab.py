"""HD-2D rendering lab (Milestone 16 Stage 1): real 3D geometry from a Blender-exported GLB, pixel-art textures on
it, and animated 2D characters standing in it, with occlusion from a real depth buffer.

Everything renders off-screen through Arcade's own OpenGL layer (``arcade.gl``) in a hidden window: no second
engine, no window on the desktop. Coordinates are metres, Z up: x east, y north (Mesh's map y), z height;
one metre is one 32 px tile.

    py -3.13 tooling/hd2d_lab/lab.py OUT_DIR [--ortho]    renders the evidence frames, a GIF and timings
"""

from __future__ import annotations

import json
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))  # the engine's optional_arcade (Mesh imports arcade only through it)
ASSETS = HERE / "assets"
STRUCTURE = ASSETS / "stone_outpost.glb"
HERO_SHEET = REPO / "assets" / "sprites" / "starter_hero.png"  # Mesh's own generated art (docs/starter_art.md)
VILLAGER_SHEET = REPO / "assets" / "sprites" / "starter_villager.png"
FRAME_W, FRAME_H, ROWS = 32, 48, ("down", "left", "right", "up")
PX = 1.0 / 32.0  # metres per sprite pixel: a 32 x 48 frame is 1.0 x 1.5 m

MESH_VS = """
#version 330
uniform mat4 u_vp; uniform mat4 u_model;
in vec3 in_pos; in vec3 in_nrm; in vec2 in_uv;
out vec3 v_nrm; out vec2 v_uv;
void main() { v_nrm = mat3(u_model) * in_nrm; v_uv = in_uv; gl_Position = u_vp * u_model * vec4(in_pos, 1.0); }
"""
MESH_FS = """
#version 330
uniform sampler2D u_tex; uniform vec3 u_sun; uniform float u_ambient; uniform int u_lit;
in vec3 v_nrm; in vec2 v_uv; out vec4 f_color;
void main() {
    vec4 c = texture(u_tex, v_uv);
    float light = u_lit == 1 ? u_ambient + (1.0 - u_ambient) * max(dot(normalize(v_nrm), u_sun), 0.0) : 1.0;
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
    if (c.a < 0.5) discard;  // pixel art is binary alpha: discard, write depth for the rest, no sorting needed
    f_color = u_solid == 1 ? vec4(1.0, 0.0, 0.0, 1.0) : vec4(c.rgb * u_light, 1.0);
}
"""
SHADOW_FS = """
#version 330
in vec2 v_uv; out vec4 f_color;
void main() { float d = length(v_uv - 0.5) * 2.0; if (d > 1.0) discard; f_color = vec4(0.0, 0.0, 0.0, 0.35 * (1.0 - d * d)); }
"""


def perspective(fov_deg: float, aspect: float, near: float, far: float) -> np.ndarray:
    f = 1.0 / math.tan(math.radians(fov_deg) / 2)
    return np.array([[f / aspect, 0, 0, 0], [0, f, 0, 0],
                     [0, 0, (far + near) / (near - far), 2 * far * near / (near - far)], [0, 0, -1, 0]])


def orthographic(half_h: float, aspect: float, near: float, far: float) -> np.ndarray:
    half_w = half_h * aspect
    return np.array([[1 / half_w, 0, 0, 0], [0, 1 / half_h, 0, 0],
                     [0, 0, -2 / (far - near), -(far + near) / (far - near)], [0, 0, 0, 1]])


def look_at(eye: np.ndarray, target: np.ndarray, up=(0.0, 0.0, 1.0)) -> np.ndarray:
    f = target - eye
    f = f / np.linalg.norm(f)
    s = np.cross(f, up)
    s = s / np.linalg.norm(s)
    u = np.cross(s, f)
    m = np.eye(4)
    m[0, :3], m[1, :3], m[2, :3] = s, u, -f
    m[:3, 3] = -m[:3, :3] @ eye
    return m


def _image(path: Path) -> Image.Image:
    with Image.open(path) as img:
        return img.convert("RGBA")


def _mat(m: np.ndarray) -> tuple[float, ...]:
    return tuple(float(v) for v in m.T.flatten())  # GL wants column-major


@dataclass
class Camera:
    target: tuple[float, float, float] = (0.0, 0.5, 0.8)
    distance: float = 15.0
    pitch_deg: float = 32.0  # elevation above the ground plane
    yaw_deg: float = 0.0  # 0: looking north
    fov_deg: float = 30.0  # narrow, as HD-2D does
    ortho: bool = False

    def eye(self) -> np.ndarray:
        p, y = math.radians(self.pitch_deg), math.radians(self.yaw_deg)
        back = np.array([-math.sin(y) * math.cos(p), -math.cos(y) * math.cos(p), math.sin(p)])
        return np.array(self.target) + back * self.distance

    def right(self) -> np.ndarray:
        y = math.radians(self.yaw_deg)
        return np.array([math.cos(y), -math.sin(y), 0.0])

    def view_projection(self, aspect: float) -> np.ndarray:
        proj = orthographic(self.distance * math.tan(math.radians(self.fov_deg) / 2), aspect, 0.1, 100.0) \
            if self.ortho else perspective(self.fov_deg, aspect, 0.1, 100.0)
        return proj @ look_at(self.eye(), np.array(self.target))


@dataclass
class Character:
    sheet: str  # "hero" or "villager"
    x: float
    y: float
    z: float = 0.0
    facing: str = "down"
    frame: int = 0


class Lab:
    def __init__(self, size: tuple[int, int] = (960, 540), *, window=None) -> None:
        from engine import optional_arcade

        arcade = optional_arcade.arcade
        self.arcade = arcade
        self.window = window or arcade.Window(size[0], size[1], "HD-2D lab", visible=False)
        self.ctx, self.size = self.window.ctx, size
        self.fbo = self.ctx.framebuffer(color_attachments=[self.ctx.texture(size, components=4)],
                                        depth_attachment=self.ctx.depth_texture(size))
        self.mesh_prog = self.ctx.program(vertex_shader=MESH_VS, fragment_shader=MESH_FS)
        self.sprite_prog = self.ctx.program(vertex_shader=SPRITE_VS, fragment_shader=SPRITE_FS)
        self.shadow_prog = self.ctx.program(vertex_shader=SPRITE_VS, fragment_shader=SHADOW_FS)
        self.structures: list[tuple] = []  # (geometry, texture)
        hero = _image(HERO_SHEET)
        self.sheets = {"hero": self._texture(hero), "villager": self._texture(_image(VILLAGER_SHEET))}
        self.sheet_size = hero.size
        self.ground = self._ground(_image(ASSETS / "grass.png"), half=14.0)
        self.camera = Camera()
        self.sun = np.array([-0.45, -0.55, 0.70]) / np.linalg.norm([-0.45, -0.55, 0.70])
        self.ambient, self.lit = 0.55, True
        self.show_structure = True

    # ------------------------------------------------------------------ resources
    def _texture(self, image: Image.Image, repeat: bool = False):
        gl = self.ctx
        tex = gl.texture(image.size, components=4, data=image.tobytes(), filter=(gl.NEAREST, gl.NEAREST))
        tex.wrap_x = tex.wrap_y = gl.REPEAT if repeat else gl.CLAMP_TO_EDGE
        return tex

    def load_structure(self, path: Path = STRUCTURE) -> None:
        from hd2d_lab.gltf import load_glb

        for prim in load_glb(path).primitives:
            data = np.hstack([prim.positions, prim.normals, prim.uvs]).astype("f4")
            geometry = self.ctx.geometry(
                [self.arcade.gl.BufferDescription(self.ctx.buffer(data=data.tobytes()), "3f 3f 2f",
                                                  ["in_pos", "in_nrm", "in_uv"])],
                index_buffer=self.ctx.buffer(data=prim.indices.astype("u4").tobytes()), index_element_size=4)
            image = prim.material.image or Image.new("RGBA", (1, 1), (200, 200, 200, 255))
            self.structures.append((geometry, self._texture(image, repeat=prim.material.repeat)))

    def _ground(self, image: Image.Image, half: float):
        verts = np.array([[-half, -half, 0, 0, 0, 1, -half, -half], [half, -half, 0, 0, 0, 1, half, -half],
                          [half, half, 0, 0, 0, 1, half, half], [-half, half, 0, 0, 0, 1, -half, half]], dtype="f4")
        geometry = self.ctx.geometry(
            [self.arcade.gl.BufferDescription(self.ctx.buffer(data=verts.tobytes()), "3f 3f 2f",
                                              ["in_pos", "in_nrm", "in_uv"])],
            index_buffer=self.ctx.buffer(data=np.array([0, 1, 2, 0, 2, 3], dtype="u4").tobytes()), index_element_size=4)
        return geometry, self._texture(image, repeat=True)

    # ------------------------------------------------------------------ drawing
    def _batch(self, corners: np.ndarray, uvs: np.ndarray):
        """One geometry for many quads: corners (n, 4, 3) and uvs (n, 4, 2), each quad bottom-left, bottom-right,
        top-left, top-right. One buffer and one draw call however many characters there are."""
        n = len(corners)
        data = np.concatenate([corners, uvs], axis=2).reshape(n * 4, 5).astype("f4")
        quad = np.array([0, 1, 2, 2, 1, 3], dtype="u4")
        index = (quad[None, :] + (np.arange(n, dtype="u4") * 4)[:, None]).reshape(-1)
        return self.ctx.geometry(
            [self.arcade.gl.BufferDescription(self.ctx.buffer(data=data.tobytes()), "3f 2f", ["in_pos", "in_uv"])],
            index_buffer=self.ctx.buffer(data=index.tobytes()), index_element_size=4)

    def _billboards(self, chars: list[Character]):
        """Upright quads at the characters' feet, turned to face the camera about the vertical axis (cylindrical
        billboards). Seen from a camera pitched p degrees down, an upright quad looks cos(p) as tall, so its height
        is stretched by 1 / cos(p): the sprite keeps its drawn proportions on screen."""
        w = FRAME_W * PX
        h = FRAME_H * PX / max(0.5, math.cos(math.radians(self.camera.pitch_deg)))
        r = self.camera.right() * (w / 2)
        up = np.array([0.0, 0.0, h])
        base = np.array([[c.x, c.y, c.z] for c in chars])
        corners = np.stack([base - r, base + r, base - r + up, base + r + up], axis=1)
        sw, sh = self.sheet_size
        cols = np.array([c.frame % 4 for c in chars])
        rows = np.array([ROWS.index(c.facing) for c in chars])
        u0, u1 = cols * FRAME_W / sw, (cols + 1) * FRAME_W / sw
        vt, vb = rows * FRAME_H / sh, (rows + 1) * FRAME_H / sh
        uvs = np.stack([np.c_[u0, vb], np.c_[u1, vb], np.c_[u0, vt], np.c_[u1, vt]], axis=1)
        return self._batch(corners, uvs)

    def _shadows(self, chars: list[Character]):
        s = np.array([0.42, 0.42 * 0.6, 0.0])
        base = np.array([[c.x, c.y, c.z + 0.01] for c in chars])
        corners = np.stack([base + s * [-1, -1, 0], base + s * [1, -1, 0], base + s * [-1, 1, 0], base + s * [1, 1, 0]],
                           axis=1)
        uvs = np.broadcast_to(np.array([[0, 0], [1, 0], [0, 1], [1, 1]], dtype="f4"), (len(chars), 4, 2))
        return self._batch(corners, uvs)

    def render(self, characters: list[Character], *, solid: Character | None = None, read: bool = True):
        """The scene as one image. With ``solid``, the scene's colour is cleared after its depth is written and only
        that character is drawn, in flat red: its red pixels are exactly the part of it that's visible."""
        gl = self.ctx
        vp = _mat(self.camera.view_projection(self.size[0] / self.size[1]))
        self.fbo.use()
        self.fbo.clear(color=(118, 160, 214, 255), depth=1.0)
        gl.enable(gl.DEPTH_TEST)
        gl.disable(gl.CULL_FACE)
        mp = self.mesh_prog
        mp["u_vp"] = vp
        mp["u_model"] = _mat(np.eye(4))
        mp["u_sun"] = tuple(self.sun)
        mp["u_ambient"] = self.ambient
        mp["u_lit"] = 1 if self.lit else 0
        items = [self.ground] + (self.structures if self.show_structure else [])
        for geometry, tex in items:
            tex.use(0)
            geometry.render(mp)
        if solid is not None:
            self._clear_colour_keep_depth()
        sp = self.sprite_prog
        sp["u_vp"] = vp
        sp["u_light"] = self.ambient + (1 - self.ambient) * 0.75 if self.lit else 1.0
        if solid is None:  # blob shadows: blended, depth-tested, no depth writes
            self.shadow_prog["u_vp"] = vp
            with gl.enabled(gl.BLEND):
                self.fbo.depth_mask = False
                if characters:
                    self._shadows(characters).render(self.shadow_prog)
                self.fbo.depth_mask = True
        sp["u_solid"] = 1 if solid is not None else 0
        drawn = [solid] if solid is not None else characters
        for sheet in sorted({c.sheet for c in drawn}):
            self.sheets[sheet].use(0)
            self._billboards([c for c in drawn if c.sheet == sheet]).render(sp)
        gl.disable(gl.DEPTH_TEST)
        if not read:  # draw only (a game shows the frame; reading pixels back is just for the evidence)
            self.window.use()
            return None
        data = self.fbo.read(components=3)
        self.window.use()
        return Image.frombytes("RGB", self.size, data).transpose(Image.Transpose.FLIP_TOP_BOTTOM)

    def _clear_colour_keep_depth(self) -> None:
        """Clear the colour to black and keep the depth just written (glClear honours the depth mask)."""
        self.fbo.depth_mask = False
        self.fbo.clear(color=(0, 0, 0, 255))
        self.fbo.depth_mask = True

    def visible_pixels(self, c: Character) -> int:
        """How many of the character's pixels pass the depth test against the scene."""
        image = np.asarray(self.render([], solid=c))
        return int(((image[:, :, 0] > 200) & (image[:, :, 1] < 60)).sum())

    def total_pixels(self, c: Character) -> int:
        """The character's pixels with nothing in the way (the structure hidden)."""
        shown, self.show_structure = self.show_structure, False
        try:
            return self.visible_pixels(c)
        finally:
            self.show_structure = shown

    def frame_ms(self, characters: list[Character], frames: int = 60, structures: int = 1) -> float:
        """Average time per frame (ms) to draw the scene, finished on the GPU (no pixel read-back), with
        ``structures`` copies of the building drawn (overlapping: the same geometry and fill cost)."""
        extra = self.structures * (structures - 1)
        saved = self.structures
        self.structures = saved + extra
        try:
            self.render(characters, read=False)
            self.ctx.finish()
            start = time.perf_counter()
            for _ in range(frames):
                self.render(characters, read=False)
            self.ctx.finish()
            return (time.perf_counter() - start) * 1000 / frames
        finally:
            self.structures = saved


def walk_path(t: float) -> tuple[float, float, str]:
    """A loop around the outpost: in front (south), up the east side, behind it (north), down the west side."""
    pts = [(-3.2, -3.4), (3.2, -3.4), (3.2, 3.6), (-3.2, 3.6)]
    facings = ["right", "up", "left", "down"]
    lengths = [math.dist(pts[i], pts[(i + 1) % 4]) for i in range(4)]
    d = (t % 1.0) * sum(lengths)
    for i, seg in enumerate(lengths):
        if d <= seg:
            a, b = pts[i], pts[(i + 1) % 4]
            k = d / seg
            return a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k, facings[i]
        d -= seg
    return pts[0][0], pts[0][1], facings[0]


def main(out: Path, ortho: bool = False) -> dict:
    import pyglet

    _init = pyglet.window.Window.__init__
    pyglet.window.Window.__init__ = lambda self, *a, **k: _init(self, *a, **{**k, "visible": False})
    import engine.optional_arcade  # noqa: F401  # DPI-unaware first, as Mesh runs

    out.mkdir(parents=True, exist_ok=True)
    lab = Lab()
    lab.camera.ortho = ortho
    lab.load_structure()
    villager = Character("villager", 1.6, -0.6, 1.0, "down")  # standing on the raised platform (z = 1 m)
    results: dict = {"gl": {"version": lab.ctx.gl_version, "renderer": lab.ctx.info.RENDERER,
                            "max_texture": lab.ctx.info.MAX_TEXTURE_SIZE}, "ortho": ortho}

    # Key moments: in front of the outpost, half behind its east corner, fully behind it.
    shots = {"front": Character("hero", 0.2, -3.2, 0.0, "up"), "corner": Character("hero", 2.25, 1.6, 0.0, "up"),
             "behind": Character("hero", 0.0, 2.5, 0.0, "down")}
    results["occlusion"] = {}
    for name, hero in shots.items():
        lab.render([hero, villager]).save(out / f"{name}.png")
        visible, total = lab.visible_pixels(hero), lab.total_pixels(hero)
        results["occlusion"][name] = {"visible": visible, "total": total, "share": round(visible / max(total, 1), 3)}
    results["villager_on_platform"] = {"visible": lab.visible_pixels(villager), "total": lab.total_pixels(villager)}

    # The walk around the outpost, as a GIF (the hero animates its 4-frame walk).
    frames = []
    for i in range(48):
        x, y, facing = walk_path(i / 48)
        hero = Character("hero", x, y, 0.0, facing, frame=(i // 3) % 4)
        frames.append(lab.render([hero, villager]).resize((480, 270), Image.Resampling.NEAREST))
    frames[0].save(out / "walk.gif", save_all=True, append_images=frames[1:], duration=90, loop=0)

    # The camera moving round the scene (proving real 3D, not a painted backdrop).
    orbit = []
    for yaw in (-40, -20, 0, 20, 40):
        lab.camera.yaw_deg = yaw
        orbit.append(lab.render([shots["corner"], villager]).resize((384, 216), Image.Resampling.NEAREST))
    lab.camera.yaw_deg = 0
    sheet = Image.new("RGB", (384 * 5, 216))
    for i, im in enumerate(orbit):
        sheet.paste(im, (i * 384, 0))
    sheet.save(out / "orbit.png")

    # Timings: the lab scene, then 25 outposts and 300 characters.
    crowd = [Character("hero" if i % 2 else "villager", -12 + (i % 20) * 1.2, -10 + (i // 20) * 1.3, 0.0,
                       ROWS[i % 4], i % 4) for i in range(300)]
    results["frame_ms"] = {"lab_scene": round(lab.frame_ms([shots["front"], villager]), 3),
                           "25_outposts_300_characters": round(lab.frame_ms(crowd, frames=30, structures=25), 3)}
    (out / "results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    lab.window.close()
    return results


if __name__ == "__main__":
    print(json.dumps(main(Path(sys.argv[1]), ortho="--ortho" in sys.argv), indent=1))
