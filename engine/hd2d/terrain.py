"""Sculpted ground for HD-2D rooms (Milestone 20A, feasibility): a heightfield over the room's ground.

The ground (``settings.hd2d.ground``) may carry ``"terrain"``: heights at the corners of a grid of square cells across
it, ``cell`` px apart (16 px, 0.5 m, by default), offset from the ground's elevation. Everything else is the ground as
it was: its texture, extent and elevation. A room without terrain, or with all of it flat, is the flat ground exactly.

    "ground": {"texture": "...", "from": [0, 0], "to": [1024, 768], "elevation": 0,
               "terrain": {"cell": 16, "chunks": {"0,0": "<base64>", "3,1": "<base64>"}}}

- **Storage, deterministic and sparse.** The corners are kept in chunks of ``CHUNK`` x ``CHUNK``; a chunk owns the
  corners (i, j) with i // CHUNK, j // CHUNK its key. Each is little-endian int16 heights in quarters of a px
  (0.78 cm; +-256 m), row by row, base64; an all-zero chunk is left out, and the keys are sorted. The same heights
  always write the same text, so saves diff cleanly and undo compares exactly.
- **Height** (``height``): each cell is two triangles split along its (i, j)-(i+1, j+1) diagonal, linear across each:
  exactly what is drawn (``chunk_mesh``) and walked on (``chunk_surfaces``).
- **Edits** (``sculpt``): raise, lower, smooth and flatten within a radius, with a soft cosine falloff; each returns
  the chunks whose drawing and collision change (a corner on a chunk's edge is shared with its neighbours).
- **Drawing:** per chunk a mesh in the ground's own vertex format (position, normal, uv): the ground's texture on
  gentle ground (its uv the world's metres, as the flat ground), a second texture (dirt) on faces steeper than
  ``STEEP`` (uv box-mapped onto the face's side, so its texels keep their size).
- **Walking** (``engine.hd2d.world``): its triangles are solid walkable surfaces, like the flat ground's, except those
  steeper than ``MAX_SLOPE``: nobody stands on them, so they stop characters (a cliff). Structures, floors, stairs and
  bridges stand on it as they stand on the flat ground; caves, overhangs and stacked walkable surfaces are theirs to
  provide: a heightfield has one height per place.
"""

from __future__ import annotations

import base64
import math
import sys
from array import array
from dataclasses import dataclass, field
from typing import Any

PX = 32.0  # px per metre
CHUNK = 16  # cells (and corners) per chunk side
QUANTUM = 0.25  # px: a stored height's step
LIMIT = 32767 * 0.25  # px (about 256 m): the most a corner may be raised or lowered (its int16 store's limit)
CELLS = (8, 16, 32)  # px: the cell sizes a terrain may use
STEEP = 0.75  # a face's normal z below this (about 41 degrees) is drawn as dirt
MAX_SLOPE = 0.7  # a face's normal z below this (about 46 degrees) can't be stood on
TOOLS = ("raise", "lower", "smooth", "flatten")


class TerrainError(ValueError):
    """Terrain settings or an edit that can't be used."""


@dataclass
class Terrain:
    """A ground's heights. ``origin`` and ``cell`` in px; ``heights`` px above the ground's ``base`` (px), corner
    (i, j) at ``i + j * (nx + 1)``."""

    origin: tuple[float, float]
    size: tuple[float, float]  # the ground's extent (px)
    base: float
    cell: int = 16
    heights: list[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.nx = max(1, math.ceil(self.size[0] / self.cell))
        self.ny = max(1, math.ceil(self.size[1] / self.cell))
        if not self.heights:
            self.heights = [0.0] * ((self.nx + 1) * (self.ny + 1))

    # ------------------------------------------------------------------ storage
    @classmethod
    def from_ground(cls, ground: Any) -> Terrain:
        """The terrain of a parsed ground (``engine.hd2d.settings.Ground``); flat if it has none."""
        raw = getattr(ground, "terrain", None) or {}
        cell = int(raw.get("cell", 16))
        size = (ground.hi[0] - ground.lo[0], ground.hi[1] - ground.lo[1])
        terrain = cls((float(ground.lo[0]), float(ground.lo[1])), size, float(ground.elevation), cell)
        terrain.load_chunks(raw.get("chunks") or {})
        return terrain

    def chunk_count(self) -> tuple[int, int]:
        return (self.nx + 1 + CHUNK - 1) // CHUNK, (self.ny + 1 + CHUNK - 1) // CHUNK

    def load_chunks(self, chunks: dict[str, str]) -> None:
        cx_n, cy_n = self.chunk_count()
        for key, text in chunks.items():
            ci, cj = parse_key(key)
            if not (0 <= ci < cx_n and 0 <= cj < cy_n):
                raise TerrainError(f"terrain chunk '{key}' lies outside the ground")
            try:
                data = base64.b64decode(text, validate=True)
            except (ValueError, TypeError) as exc:
                raise TerrainError(f"terrain chunk '{key}' isn't base64") from exc
            if len(data) != CHUNK * CHUNK * 2:
                raise TerrainError(f"terrain chunk '{key}' has {len(data)} bytes (expected {CHUNK * CHUNK * 2})")
            values = array("h")
            values.frombytes(data)
            if sys.byteorder == "big":
                values.byteswap()
            for k, v in enumerate(values):
                i, j = ci * CHUNK + k % CHUNK, cj * CHUNK + k // CHUNK
                if i <= self.nx and j <= self.ny:
                    self.heights[i + j * (self.nx + 1)] = v * QUANTUM

    def chunks(self) -> dict[str, str]:
        """The heights as stored: non-flat chunks only, sorted, deterministic."""
        out = {}
        cx_n, cy_n = self.chunk_count()
        for cj in range(cy_n):
            for ci in range(cx_n):
                values = array("h", [0] * (CHUNK * CHUNK))
                any_set = False
                for k in range(CHUNK * CHUNK):
                    i, j = ci * CHUNK + k % CHUNK, cj * CHUNK + k // CHUNK
                    if i <= self.nx and j <= self.ny:
                        q = int(round(self.heights[i + j * (self.nx + 1)] / QUANTUM))
                        values[k] = q
                        any_set = any_set or q != 0
                if any_set:
                    if sys.byteorder == "big":
                        values.byteswap()
                    out[f"{ci},{cj}"] = base64.b64encode(values.tobytes()).decode("ascii")
        return dict(sorted(out.items(), key=lambda kv: parse_key(kv[0])[::-1]))

    def settings(self) -> dict[str, Any]:
        """``ground.terrain`` as saved (None when flat: the plain ground)."""
        chunks = self.chunks()
        return {"cell": self.cell, "chunks": chunks} if chunks else {}

    # ------------------------------------------------------------------ heights
    def corner(self, i: int, j: int) -> float:
        i, j = min(max(i, 0), self.nx), min(max(j, 0), self.ny)
        return self.heights[i + j * (self.nx + 1)]

    def corner_xy(self, i: int, j: int) -> tuple[float, float]:
        """Corner (i, j)'s place (px); the last row and column end at the ground's edge."""
        return (self.origin[0] + min(i * self.cell, self.size[0]), self.origin[1] + min(j * self.cell, self.size[1]))

    def height(self, x: float, y: float) -> float | None:
        """The ground's height (px, its elevation included) at (x, y) px; None off the ground."""
        u, v = (x - self.origin[0]) / self.cell, (y - self.origin[1]) / self.cell
        if u < -1e-6 or v < -1e-6 or x > self.origin[0] + self.size[0] + 1e-6 or y > self.origin[1] + self.size[1] + 1e-6:
            return None
        i, j = min(int(u), self.nx - 1), min(int(v), self.ny - 1)
        (x0, y0), (x1, y1) = self.corner_xy(i, j), self.corner_xy(i + 1, j + 1)
        fu = (x - x0) / max(1e-9, x1 - x0)
        fv = (y - y0) / max(1e-9, y1 - y0)
        h00, h10, h01, h11 = self.corner(i, j), self.corner(i + 1, j), self.corner(i, j + 1), self.corner(i + 1, j + 1)
        if fu >= fv:
            h = h00 + fu * (h10 - h00) + fv * (h11 - h10)
        else:
            h = h00 + fu * (h11 - h01) + fv * (h01 - h00)
        return self.base + h

    def surface_at(self, x: float, y: float) -> tuple[float, float] | None:
        """The ground at (x, y) px: its height (px, its elevation included) and how upright its face is there (the
        normal's z: 1 level, MAX_SLOPE and below too steep to stand on); None off the ground. What collision reads,
        a lookup, not a search through triangles."""
        u, v = (x - self.origin[0]) / self.cell, (y - self.origin[1]) / self.cell
        if u < -1e-6 or v < -1e-6 or x > self.origin[0] + self.size[0] + 1e-6 or y > self.origin[1] + self.size[1] + 1e-6:
            return None
        i, j = min(int(u), self.nx - 1), min(int(v), self.ny - 1)
        (x0, y0), (x1, y1) = self.corner_xy(i, j), self.corner_xy(i + 1, j + 1)
        w, d = max(1e-9, x1 - x0), max(1e-9, y1 - y0)
        fu, fv = (x - x0) / w, (y - y0) / d
        h00, h10, h01, h11 = self.corner(i, j), self.corner(i + 1, j), self.corner(i, j + 1), self.corner(i + 1, j + 1)
        if fu >= fv:
            h = h00 + fu * (h10 - h00) + fv * (h11 - h10)
            gx, gy = (h10 - h00) / w, (h11 - h10) / d
        else:
            h = h00 + fu * (h11 - h01) + fv * (h01 - h00)
            gx, gy = (h11 - h01) / w, (h01 - h00) / d
        return self.base + h, 1.0 / math.sqrt(1.0 + gx * gx + gy * gy)

    def is_flat(self) -> bool:
        return not any(self.heights)

    # ------------------------------------------------------------------ edits
    def sculpt(self, tool: str, x: float, y: float, radius: float, strength: float,
               target: float | None = None) -> set[tuple[int, int]]:
        """One brush stroke at (x, y) px: ``raise`` / ``lower`` by up to ``strength`` px at its centre; ``smooth``
        towards the neighbours' mean, ``flatten`` towards ``target`` px (the height at the centre if None), by up to
        ``strength`` (0-1) of the way. ``radius`` px; a cosine falloff to its edge. Returns the chunks to redraw."""
        if tool not in TOOLS:
            raise TerrainError(f"terrain tool must be one of {', '.join(TOOLS)} (got {tool!r})")
        if target is None and tool == "flatten":
            here = self.height(x, y)
            target = (here if here is not None else self.base) - self.base
        elif target is not None:
            target -= self.base
        r_cells = radius / self.cell
        ci, cj = (x - self.origin[0]) / self.cell, (y - self.origin[1]) / self.cell
        i0, i1 = max(0, math.floor(ci - r_cells)), min(self.nx, math.ceil(ci + r_cells))
        j0, j1 = max(0, math.floor(cj - r_cells)), min(self.ny, math.ceil(cj + r_cells))
        before = list(self.heights) if tool == "smooth" else self.heights
        changed: set[tuple[int, int]] = set()
        for j in range(j0, j1 + 1):
            for i in range(i0, i1 + 1):
                px, py = self.corner_xy(i, j)
                d = math.hypot(px - x, py - y)
                if d >= radius:
                    continue
                w = 0.5 * (1.0 + math.cos(math.pi * d / radius))
                k = i + j * (self.nx + 1)
                h = before[k]
                if tool == "raise":
                    new = h + strength * w
                elif tool == "lower":
                    new = h - strength * w
                elif tool == "smooth":
                    mean = (sum(before[ii + jj * (self.nx + 1)] for ii, jj in ((i - 1, j), (i + 1, j), (i, j - 1), (i, j + 1))
                                if 0 <= ii <= self.nx and 0 <= jj <= self.ny)
                            / sum(1 for ii, jj in ((i - 1, j), (i + 1, j), (i, j - 1), (i, j + 1))
                                  if 0 <= ii <= self.nx and 0 <= jj <= self.ny))
                    new = h + min(1.0, strength) * w * (mean - h)
                else:
                    assert target is not None
                    new = h + min(1.0, strength) * w * (target - h)
                new = round(max(-LIMIT, min(LIMIT, new)) / QUANTUM) * QUANTUM
                if new != self.heights[k]:
                    self.heights[k] = new
                    changed.add((i, j))
        return chunks_of(changed)

    # ------------------------------------------------------------------ geometry
    def chunk_cells(self, ci: int, cj: int) -> tuple[range, range]:
        return range(ci * CHUNK, min(self.nx, (ci + 1) * CHUNK)), range(cj * CHUNK, min(self.ny, (cj + 1) * CHUNK))

    def _point(self, i: int, j: int) -> tuple[float, float, float]:
        x, y = self.corner_xy(i, j)
        return x / PX, y / PX, (self.base + self.corner(i, j)) / PX

    def _cell_triangles(self, i: int, j: int) -> tuple[tuple[tuple[float, float, float], ...], ...]:
        a, b, c, d = self._point(i, j), self._point(i + 1, j), self._point(i + 1, j + 1), self._point(i, j + 1)
        return (a, b, c), (a, c, d)

    def chunk_flat(self, ci: int, cj: int) -> float | None:
        """The chunk's one height (px above the base) if every corner it draws is level, else None."""
        cells_i, cells_j = self.chunk_cells(ci, cj)
        first = self.corner(cells_i.start, cells_j.start)
        for j in range(cells_j.start, cells_j.stop + 1):
            for i in range(cells_i.start, cells_i.stop + 1):
                if self.corner(i, j) != first:
                    return None
        return first

    def chunk_triangles(self, ci: int, cj: int) -> list[tuple[tuple[float, float, float], ...]]:
        """The chunk's triangles (m); a level chunk is two."""
        cells_i, cells_j = self.chunk_cells(ci, cj)
        if not cells_i or not cells_j:
            return []
        if self.chunk_flat(ci, cj) is not None:
            a, c = self._point(cells_i.start, cells_j.start), self._point(cells_i.stop, cells_j.stop)
            b, d = self._point(cells_i.stop, cells_j.start), self._point(cells_i.start, cells_j.stop)
            return [(a, b, c), (a, c, d)]
        return [t for j in cells_j for i in cells_i for t in self._cell_triangles(i, j)]

    def _normal_at(self, i: int, j: int) -> tuple[float, float, float]:
        dx = (self.corner(i + 1, j) - self.corner(i - 1, j)) / (2 * self.cell)
        dy = (self.corner(i, j + 1) - self.corner(i, j - 1)) / (2 * self.cell)
        n = math.sqrt(dx * dx + dy * dy + 1.0)
        return -dx / n, -dy / n, 1.0 / n

    def chunk_mesh(self, ci: int, cj: int) -> tuple[array, array]:
        """The chunk's vertices (x, y, z, nx, ny, nz, u, v; 8 floats each, three per triangle), as two lists: the
        ground's texture's (gentle cells) and dirt's (a cell either of whose faces is steeper than STEEP: one material
        a cell, so their boundary follows the cells, not a sawtooth of triangles), and, on the ground's border, a dirt
        skirt down to below its lowest point, so ground cut by the room's edge isn't a paper shell."""
        gentle, steep = array("f"), array("f")
        cells_i, cells_j = self.chunk_cells(ci, cj)
        for j in cells_j:
            for i in cells_i:
                corners = ((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1))
                tris = [[self._point(*corners[t]) for t in tri] for tri in ((0, 1, 2), (0, 2, 3))]
                faces = [_face_normal(*pts) for pts in tris]
                out = steep if min(f[2] for f in faces) < STEEP else gentle
                for tri, pts, face in zip(((0, 1, 2), (0, 2, 3)), tris, faces):
                    for t, p in zip(tri, pts):
                        n = self._normal_at(*corners[t])
                        if out is steep:  # box-mapped onto the face's side: texels keep their size on a cliff
                            uv = (p[1], p[2]) if abs(face[0]) > abs(face[1]) else (p[0], p[2])
                        else:
                            uv = (p[0], p[1])
                        out.extend((p[0], p[1], p[2], n[0], n[1], n[2], uv[0], uv[1]))
        self._skirt(ci, cj, steep)
        return gentle, steep

    def _skirt(self, ci: int, cj: int, out: array) -> None:
        """The border's side wall within this chunk, where the ground there leaves its base level: between the ground
        and the base (and a little below), so a hill cut by the room's edge, or a hollow, is closed, not a paper
        shell. Level border stays as the flat ground's edge. Only this chunk's own corners decide it."""
        cells_i, cells_j = self.chunk_cells(ci, cj)
        edges = []
        if cells_j and cells_j.start == 0:
            edges += [((i + 1, 0), (i, 0), (0.0, -1.0)) for i in cells_i]
        if cells_j and cells_j.stop == self.ny:
            edges += [((i, self.ny), (i + 1, self.ny), (0.0, 1.0)) for i in cells_i]
        if cells_i and cells_i.start == 0:
            edges += [((0, j), (0, j + 1), (-1.0, 0.0)) for j in cells_j]
        if cells_i and cells_i.stop == self.nx:
            edges += [((self.nx, j + 1), (self.nx, j), (1.0, 0.0)) for j in cells_j]
        base = self.base / PX
        for a, b, (nx, ny) in edges:
            if self.corner(*a) == 0.0 and self.corner(*b) == 0.0:
                continue
            pa, pb = self._point(*a), self._point(*b)
            ta, tb = (pa[0], pa[1], max(pa[2], base)), (pb[0], pb[1], max(pb[2], base))
            ba, bb = (pa[0], pa[1], min(pa[2], base) - 0.25), (pb[0], pb[1], min(pb[2], base) - 0.25)
            for q in (ta, tb, bb, ta, bb, ba):
                out.extend((q[0], q[1], q[2], nx, ny, 0.0, q[1] if nx else q[0], q[2]))

    def chunk_surfaces(self, ci: int, cj: int) -> list[tuple[tuple[float, float, float], ...]]:
        """The chunk's triangles a character may stand on (m): all but the too-steep ones."""
        return [t for t in self.chunk_triangles(ci, cj) if _face_normal(*t)[2] >= MAX_SLOPE]

    def ray(self, origin: tuple[float, float, float], direction: tuple[float, float, float],
            far: float = 400.0) -> tuple[float, float, float] | None:
        """Where a ray (metres) first meets the ground, if it does: marched half a cell at a time, then halved down to
        a millimetre (what a click in Mesh Studio's 3D view points at)."""
        step = self.cell / PX / 2
        t, below_prev = 0.0, None
        while t < far:
            x, y, z = (origin[k] + direction[k] * t for k in range(3))
            h = self.height(x * PX, y * PX)
            below = None if h is None else z <= h / PX
            if below and below_prev is False:
                lo, hi = t - step, t
                for _ in range(16):
                    mid = (lo + hi) / 2
                    hm = self.height((origin[0] + direction[0] * mid) * PX, (origin[1] + direction[1] * mid) * PX)
                    if hm is not None and origin[2] + direction[2] * mid <= hm / PX:
                        hi = mid
                    else:
                        lo = mid
                return origin[0] + direction[0] * hi, origin[1] + direction[1] * hi, origin[2] + direction[2] * hi
            below_prev = below if below is not None else below_prev
            t += step
        return None

    def range_z(self) -> tuple[float, float]:
        """The lowest and highest ground (m)."""
        return (self.base + min(self.heights)) / PX, (self.base + max(self.heights)) / PX


def _face_normal(a: tuple[float, float, float], b: tuple[float, float, float],
                 c: tuple[float, float, float]) -> tuple[float, float, float]:
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    n = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
    length = math.sqrt(n[0] * n[0] + n[1] * n[1] + n[2] * n[2]) or 1.0
    return n[0] / length, n[1] / length, n[2] / length


def parse_key(key: str) -> tuple[int, int]:
    try:
        a, b = key.split(",")
        return int(a), int(b)
    except (ValueError, AttributeError) as exc:
        raise TerrainError(f"terrain chunk keys are 'i,j' (got {key!r})") from exc


def chunks_of(corners: set[tuple[int, int]]) -> set[tuple[int, int]]:
    """The chunks whose drawing a change to these corners touches (a corner on a chunk's edge is its neighbour's
    too)."""
    out = set()
    for i, j in corners:  # its own cells' chunks, and those whose corners' normals read it (one corner further out)
        for ii in range((i - 2) // CHUNK, (i + 1) // CHUNK + 1):
            for jj in range((j - 2) // CHUNK, (j + 1) // CHUNK + 1):
                if ii >= 0 and jj >= 0:
                    out.add((ii, jj))
    return out


def parse_terrain(raw: Any, where: str = "settings.hd2d.ground.terrain") -> dict[str, Any]:
    """``ground.terrain`` checked (its cell and its chunks' keys and sizes; the heights are read with the ground)."""
    if not isinstance(raw, dict):
        raise TerrainError(f"{where} must be an object like {{\"cell\": 16, \"chunks\": {{}}}}")
    unknown = set(raw) - {"cell", "chunks"}
    if unknown:
        raise TerrainError(f"{where} has unknown keys: {', '.join(sorted(unknown))}")
    cell = raw.get("cell", 16)
    if cell not in CELLS or isinstance(cell, bool):
        raise TerrainError(f"{where}.cell must be one of {', '.join(map(str, CELLS))} px (got {cell!r})")
    chunks = raw.get("chunks", {})
    if not isinstance(chunks, dict) or not all(isinstance(v, str) for v in chunks.values()):
        raise TerrainError(f"{where}.chunks must map 'i,j' to base64 heights")
    for key in chunks:
        parse_key(key)
    return {"cell": int(cell), "chunks": dict(chunks)}
