"""A room's scattered decoration on the GPU (Milestone 20D; the data is engine.hd2d.scatter's).

Thousands of grass tufts must not each be an entity, a sprite or a draw call. The room is cut into 8 m chunks; per
chunk:

- **sprites** (grass, flowers, bushes, reeds): one static buffer of quads, four vertices each holding the
  instance's foot (on the ground), the corner's offset (m: across and up) and its uv in the foliage sheet. The vertex
  shader turns every quad to face the camera (``u_right``), so nothing is rebuilt as the view turns: one draw a chunk;
- **models** (rocks, the boulder, the branch): their parts placed and merged into one buffer per texture, drawn as
  the structures are (lit, shadowed, casting a shadow when the asset does).

Chunks outside the picture are skipped (their boxes, as the ground's), and sprite chunks further than ``SPRITE_FAR``
m from the camera too (small things far off are a few pixels). A stroke rebuilds only the chunks it touched; a
sculpted ground rebuilds the chunks over it (instances stand on the ground as it is now).
"""

from __future__ import annotations

import math
from array import array
from pathlib import Path
from typing import Any, Callable, Iterable

from PIL import Image

from engine.hd2d.lighting import LIGHTING_GLSL
from engine.hd2d.scatter import ASSETS, CELL_PX, SHEET

PX = 32.0
CHUNK_PX = 256.0  # 8 m
BLOCK = 4  # chunks a side of a block of the models' shadow casters (32 m): one caster draw a block
SPRITE_FAR = 60.0  # m from where the camera looks (its target): sprite chunks further away aren't drawn
IDENTITY = (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)

BILLBOARD_VS = """
#version 330
uniform mat4 u_vp; uniform vec3 u_right; uniform float u_stretch;
in vec3 in_pos; in vec2 in_corner; in vec2 in_uv;
out vec2 v_uv; out vec3 v_world;
void main() {
    vec3 w = in_pos + u_right * in_corner.x + vec3(0.0, 0.0, in_corner.y * u_stretch);
    v_uv = in_uv; v_world = w; gl_Position = u_vp * vec4(w, 1.0);
}
"""
BILLBOARD_FS = """
#version 330
uniform sampler2D u_tex;
in vec2 v_uv; in vec3 v_world; out vec4 f_color;
""" + LIGHTING_GLSL + """
void main() {
    vec4 c = texture(u_tex, v_uv);
    if (c.a < 0.5) discard;
    f_color = vec4(c.rgb * light_at(v_world, vec3(0.0, -1.0, 0.0), true), 1.0);
}
"""


def _cell_boxes(sheet: Image.Image) -> list[tuple[int, int, int, int] | None]:
    """Each cell's drawn box (left, top, right, bottom px within the cell), None if empty."""
    out = []
    for k in range(sheet.width // CELL_PX):
        out.append(sheet.crop((k * CELL_PX, 0, (k + 1) * CELL_PX, CELL_PX)).getchannel("A").getbbox())
    return out


class ScatterLayer:
    def __init__(self, renderer: Any, scatter: dict[str, list[tuple[int, int, int, int]]],
                 height: Callable[[float, float], float]) -> None:
        """``height(x, y)``: the ground's height (px) there, as drawn now."""
        self.r = renderer
        self.ctx = renderer.ctx
        self.height = height
        self.instances: dict[str, set[tuple[int, int, int, int]]] = {}
        self.chunks: dict[tuple[int, int], dict[str, set[tuple[int, int, int, int]]]] = {}
        self.cast: dict[tuple[int, int], array] = {}  # chunk -> its casting models' triangles (positions)
        self.blocks: dict[tuple[int, int], tuple[Any, Any]] = {}  # block -> (geometry, buffer): the casters
        self._dirty_blocks: set[tuple[int, int]] = set()
        self.centres: dict[tuple[int, int], tuple[float, float]] = {}
        self._bounds: dict[str, Any] = {}
        self.sprite_draws: dict[tuple[int, int], tuple[Any, Any]] = {}  # chunk -> (geometry, buffer)
        self.model_draws: dict[tuple[int, int], list[tuple[Any, Any, Any, bool]]] = {}  # -> (geom, buf, texture, cast)
        self.boxes: dict[tuple[int, int], tuple[tuple[float, ...], tuple[float, ...]]] = {}
        self.draw_calls = 0
        sheet = _open(renderer, SHEET)
        self.sheet_size = sheet.size if sheet is not None else (CELL_PX, CELL_PX)
        self.cells = _cell_boxes(sheet) if sheet is not None else []
        self.texture = renderer._texture(sheet if sheet is not None else Image.new("RGBA", (CELL_PX, CELL_PX)))
        self.prog = self.ctx.program(vertex_shader=BILLBOARD_VS, fragment_shader=BILLBOARD_FS)
        self.set_instances(scatter)

    # ------------------------------------------------------------------ building
    def set_instances(self, scatter: dict[str, list[tuple[int, int, int, int]]],
                      chunks: Iterable[tuple[int, int]] | None = None) -> None:
        """The scatter is now ``scatter``: rebuild ``chunks`` (all if None)."""
        self.instances = {k: set(v) for k, v in scatter.items() if v}
        by_chunk: dict[tuple[int, int], dict[str, set[tuple[int, int, int, int]]]] = {}
        for name, rows in self.instances.items():
            for row in rows:
                by_chunk.setdefault(_chunk(row[0], row[1]), {}).setdefault(name, set()).add(row)
        todo = set(by_chunk) | set(self.chunks) if chunks is None else set(chunks)
        self.chunks = by_chunk
        for key in todo:
            self._build(key)

    def apply(self, changes: Iterable[tuple[str, tuple[int, int, int, int], bool]]) -> set[tuple[int, int]]:
        """Instances added (True) or removed (False), as a brush reports them: only their chunks are rebuilt.
        Returns those chunks."""
        touched = set()
        for name, row, added in changes:
            key = _chunk(row[0], row[1])
            rows = self.chunks.setdefault(key, {}).setdefault(name, set())
            every = self.instances.setdefault(name, set())
            if added:
                rows.add(row)
                every.add(row)
            else:
                rows.discard(row)
                every.discard(row)
            touched.add(key)
        for key in touched:
            self.chunks[key] = {k: v for k, v in self.chunks[key].items() if v}
            self._build(key)
        self.instances = {k: v for k, v in self.instances.items() if v}
        return touched

    def chunks_of(self, x0: float, y0: float, x1: float, y1: float) -> set[tuple[int, int]]:
        """The chunks over a box (px)."""
        (i0, j0), (i1, j1) = _chunk(x0, y0), _chunk(x1, y1)
        return {(i, j) for i in range(i0, i1 + 1) for j in range(j0, j1 + 1)}

    def follow_ground(self, x0: float, y0: float, x1: float, y1: float) -> None:
        """The ground under the box (px) changed height: its chunks stand on it anew."""
        for key in self.chunks_of(x0, y0, x1, y1) & set(self.chunks):
            self._build(key)

    def _build(self, key: tuple[int, int]) -> None:
        self._free(key)
        rows_by_asset = self.chunks.get(key)
        self._dirty_blocks.add((key[0] // BLOCK, key[1] // BLOCK))
        self.cast.pop(key, None)
        if not rows_by_asset:
            self.boxes.pop(key, None)
            self.centres.pop(key, None)
            return
        shadow = array("f")  # (its casting models' triangles)
        sprite_v, sprite_i = array("f"), array("I")
        merged: dict[int, tuple[Any, array, array, bool]] = {}
        lo, hi = [math.inf] * 3, [-math.inf] * 3
        sw, sh = self.sheet_size
        for name, rows in sorted(rows_by_asset.items()):
            asset = ASSETS[name]
            for x, y, turn, size in sorted(rows):  # (in a fixed order: the same scatter, the same buffers)
                k = size / 100
                z = self.height(x, y) / PX
                fx, fy = x / PX, y / PX
                if asset.cell is not None:
                    cell = asset.cell[(x * 7 + y * 13) % len(asset.cell)]  # (a variant by where it stands: fixed)
                    box = self.cells[cell] if cell < len(self.cells) else None
                    if box is None:
                        continue
                    left, top, right, bottom = box
                    x0, x1 = (left - CELL_PX / 2) / PX * k, (right - CELL_PX / 2) / PX * k
                    z0, z1 = (CELL_PX - bottom) / PX * k, (CELL_PX - top) / PX * k
                    u0, u1 = (cell * CELL_PX + left) / sw, (cell * CELL_PX + right) / sw
                    if turn >= 180:  # (mirrored: half of them)
                        u0, u1, x0, x1 = u1, u0, -x1, -x0
                    v0, v1 = top / sh, bottom / sh
                    base = len(sprite_v) // 7
                    sprite_v.extend((fx, fy, z, x0, z0, u0, v1, fx, fy, z, x1, z0, u1, v1,
                                     fx, fy, z, x0, z1, u0, v0, fx, fy, z, x1, z1, u1, v0))
                    sprite_i.extend((base, base + 1, base + 2, base + 1, base + 3, base + 2))
                    reach = max(abs(x0), abs(x1))
                    for n, (a, b) in enumerate(((fx - reach, fx + reach), (fy - reach, fy + reach), (z + z0, z + z1))):
                        lo[n], hi[n] = min(lo[n], a), max(hi[n], b)
                    continue
                model = self._model(asset.model)
                if model is None:
                    continue
                c, s = math.cos(math.radians(turn)), math.sin(math.radians(turn))
                if asset.model not in self._bounds:
                    self._bounds[asset.model] = model.bounds()
                (mx0, my0, mz0), (mx1, my1, mz1) = self._bounds[asset.model]
                z = foot_height(self.height, x, y, max(abs(mx0), abs(mx1), abs(my0), abs(my1)) * k * PX * 0.7,
                                turn) / PX
                for part in model.parts:
                    texture = self.r._material_texture(asset.model, part, self.r._materials)
                    _t, verts, idx, _cast = merged.setdefault(id(texture), (texture, array("f"), array("I"),
                                                                            asset.shadow))
                    first = len(verts) // 8
                    v = part.vertices
                    placed = array("f")
                    for i in range(0, len(v), 8):
                        px, py, pz = v[i] * k, v[i + 1] * k, v[i + 2] * k
                        wx, wy, wz = fx + c * px - s * py, fy + s * px + c * py, z + pz
                        verts.extend((wx, wy, wz, c * v[i + 3] - s * v[i + 4], s * v[i + 3] + c * v[i + 4], v[i + 5],
                                      v[i + 6], v[i + 7]))
                        placed.extend((wx, wy, wz))
                    idx.extend(j + first for j in part.indices)
                    if asset.shadow:  # (its triangles, positions only, for the block's one caster draw)
                        for j in part.indices:
                            shadow.extend(placed[j * 3:j * 3 + 3])
                reach = max(abs(mx0), abs(mx1), abs(my0), abs(my1)) * k  # (its box, turned any way)
                for n, (a, b) in enumerate(((fx - reach, fx + reach), (fy - reach, fy + reach),
                                            (z + mz0 * k, z + mz1 * k))):
                    lo[n], hi[n] = min(lo[n], a), max(hi[n], b)
        gl = self.r.arcade.gl
        if sprite_i:
            buffer = self.ctx.buffer(data=sprite_v.tobytes())
            index = self.ctx.buffer(data=sprite_i.tobytes())
            geometry = self.ctx.geometry([gl.BufferDescription(buffer, "3f 2f 2f", ["in_pos", "in_corner", "in_uv"])],
                                         index_buffer=index, index_element_size=4)
            self.sprite_draws[key] = (geometry, (buffer, index))
        draws = []
        for texture, verts, idx, cast in merged.values():
            buffer = self.ctx.buffer(data=verts.tobytes())
            index = self.ctx.buffer(data=idx.tobytes())
            geometry = self.ctx.geometry([gl.BufferDescription(buffer, "3f 3f 2f", ["in_pos", "in_nrm", "in_uv"])],
                                         index_buffer=index, index_element_size=4)
            draws.append((geometry, (buffer, index), texture, cast))
        if draws:  # (none kept empty: the frame's culling looks at fewer)
            self.model_draws[key] = draws
        if shadow:
            self.cast[key] = shadow
        self.boxes[key] = ((lo[0], lo[1], lo[2]), (hi[0], hi[1], hi[2])) if lo[0] < math.inf else \
            ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
        b_lo, b_hi = self.boxes[key]
        self.centres[key] = ((b_lo[0] + b_hi[0]) / 2, (b_lo[1] + b_hi[1]) / 2)

    def _model(self, rel: str | None) -> Any:
        """A scatter model, read when first needed (a room only reads the models its scatter uses)."""
        if rel is None:
            return None
        if rel not in self.r.models:
            from engine.hd2d.glb import load_glb  # noqa: PLC0415

            path = model_path(self.r, rel)
            if path is None:
                return None
            self.r.models[rel] = load_glb(path)
        return self.r.models[rel]

    def _free(self, key: tuple[int, int]) -> None:
        sprite = self.sprite_draws.pop(key, None)
        if sprite is not None:
            sprite[0].flush()
            for b in sprite[1]:
                b.delete()
        for geometry, buffers, _t, _c in self.model_draws.pop(key, []):
            geometry.flush()
            for b in buffers:
                b.delete()

    # ------------------------------------------------------------------ drawing
    def statics(self, vp: list[list[float]] | None, in_view: Callable[..., bool]) -> list[tuple[Any, Any, tuple[float, ...]]]:
        """The model chunks in the picture, as the structures' draws (geometry, texture, matrix)."""
        return [(g, t, IDENTITY) for key, draws in self.model_draws.items()
                if vp is None or in_view(*self.boxes[key], vp) for g, _b, t, _c in draws]

    def casters(self) -> list[tuple[Any, Any, tuple[float, ...]]]:
        """What casts the sun's shadow: the models whose assets do, one position-only draw per 32 m block (a draw
        a chunk and texture cost the frame more CPU than the shadow itself)."""
        if self._dirty_blocks:
            gl = self.r.arcade.gl
            for block in self._dirty_blocks:
                self._free_block(block)
                data = array("f")
                for (i, j), tris in self.cast.items():
                    if (i // BLOCK, j // BLOCK) == block:
                        data.extend(tris)
                if data:
                    buffer = self.ctx.buffer(data=data.tobytes())
                    self.blocks[block] = (self.ctx.geometry([gl.BufferDescription(buffer, "3f", ["in_pos"])]), buffer)
            self._dirty_blocks = set()
        return [(g, None, IDENTITY) for g, _b in self.blocks.values()]

    def _free_block(self, block: tuple[int, int]) -> None:
        old = self.blocks.pop(block, None)
        if old is not None:
            old[0].flush()
            old[1].delete()

    def draw_sprites(self, vp_cols: tuple[float, ...], vp: list[list[float]], focus: tuple[float, float, float],
                     right: tuple[float, float, float], stretch: float, lighting: Any,
                     in_view: Callable[..., bool]) -> None:
        self.draw_calls = 0
        if not self.sprite_draws:
            return
        prog = self.prog
        prog["u_vp"] = vp_cols
        prog["u_right"] = right
        prog["u_stretch"] = stretch
        prog["u_tex"] = 0
        lighting.bind(prog)
        self.texture.use(0)
        far = SPRITE_FAR * SPRITE_FAR
        for key, (geometry, _b) in self.sprite_draws.items():
            cx, cy = self.centres[key]
            if (cx - focus[0]) ** 2 + (cy - focus[1]) ** 2 > far or not in_view(*self.boxes[key], vp):
                continue
            geometry.render(prog)
            self.draw_calls += 1

    # ------------------------------------------------------------------ bookkeeping
    def gl_objects(self) -> list[Any]:
        return ([self.prog] + [b for _g, bs in self.sprite_draws.values() for b in bs]
                + [b for draws in self.model_draws.values() for _g, bs, _t, _c in draws for b in bs]
                + [b for _g, b in self.blocks.values()])

    def memory_bytes(self) -> int:
        return int(sum(b.size for b in self.gl_objects()[1:]) + self.texture.width * self.texture.height * 4)

    def count(self) -> int:
        return sum(len(rows) for rows in self.instances.values())

    def release(self) -> None:
        for key in list(self.sprite_draws) + list(self.model_draws):
            self._free(key)
        for block in list(self.blocks):
            self._free_block(block)
        self.prog.delete()


def foot_height(height: Callable[[float, float], float], x: float, y: float, reach: float, turn: float) -> float:
    """Where a model stands (px): the lowest ground under it (its centre and ``reach`` px round it, along its own
    length too), so on a slope it is sunk at the high side rather than floating at the low one."""
    return min([height(x, y)] + [height(x + reach * math.cos(a), y + reach * math.sin(a))
                                 for a in (0.0, math.pi / 2, math.pi, 3 * math.pi / 2, math.radians(turn),
                                           math.radians(turn) + math.pi)])


def _chunk(x: float, y: float) -> tuple[int, int]:
    return math.floor(x / CHUNK_PX), math.floor(y / CHUNK_PX)


def _open(renderer: Any, rel: str) -> Image.Image | None:
    """A kit file from the project, else Mesh's own copy (never copied into the project), else None."""
    from engine.repo_root import bundled_file  # noqa: PLC0415

    for find in (renderer._resolve, bundled_file):
        try:
            path = find(rel)
            if path is not None and Path(path).is_file():
                with Image.open(path) as img:
                    rgba: Image.Image = img.convert("RGBA")
                    return rgba
        except (OSError, ValueError):
            continue
    return None


def model_path(renderer: Any, rel: str) -> Path | None:
    """Where a scatter model is: the project's kit, else Mesh's own."""
    from engine.repo_root import bundled_file  # noqa: PLC0415

    for find in (renderer._resolve, bundled_file):
        try:
            path = find(rel)
            if path is not None and Path(path).is_file():
                return Path(path)
        except (OSError, ValueError):
            continue
    return None
