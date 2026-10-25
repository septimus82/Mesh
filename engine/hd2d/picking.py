"""Picking in an HD-2D room (Mesh Studio's 3D view, Milestone 16 Stage 5A): what is under the mouse.

A ray from the camera through the mouse is tested against every structure's actual drawn triangles (placed, in
metres) and every character's billboard (the upright quad the renderer draws, facing the camera); the nearest hit
wins, so a structure behind another, or a character in front of a wall, is picked as one sees it, not by 2D
screen position. Structures and characters stay distinct kinds.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable

from engine.hd2d.glb import Model
from engine.hd2d.settings import PIXELS_PER_METRE, Structure

Vec = tuple[float, float, float]


@dataclass(frozen=True)
class Hit:
    kind: str  # "structure" or "sprite"
    target: Any  # the structure's id, or the sprite
    distance: float  # along the ray (m)
    point: Vec


def placement(st: Structure) -> list[list[float]]:
    """A structure's model matrix (rows; metres), as the renderer and the collision world place it."""
    c, s = math.cos(math.radians(st.rotation)), math.sin(math.radians(st.rotation))
    k = st.scale
    return [[c * k, -s * k, 0.0, st.x / PIXELS_PER_METRE], [s * k, c * k, 0.0, st.y / PIXELS_PER_METRE],
            [0.0, 0.0, k, st.elevation / PIXELS_PER_METRE], [0.0, 0.0, 0.0, 1.0]]


def _apply(m: list[list[float]], x: float, y: float, z: float) -> Vec:
    return (m[0][0] * x + m[0][1] * y + m[0][2] * z + m[0][3], m[1][0] * x + m[1][1] * y + m[1][2] * z + m[1][3],
            m[2][0] * x + m[2][1] * y + m[2][2] * z + m[2][3])


def box(st: Structure, model: Model) -> tuple[Vec, Vec]:
    """The placed structure's bounding box (m): what Mesh Studio outlines when it is selected."""
    m = placement(st)
    lo, hi = model.bounds()
    pts = [_apply(m, x, y, z) for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]
    return ((min(p[0] for p in pts), min(p[1] for p in pts), min(p[2] for p in pts)),
            (max(p[0] for p in pts), max(p[1] for p in pts), max(p[2] for p in pts)))


def box_edges(lo: Vec, hi: Vec) -> list[Vec]:
    """The 12 edges of a box as line-segment endpoint pairs."""
    c = [(x, y, z) for z in (lo[2], hi[2]) for y in (lo[1], hi[1]) for x in (lo[0], hi[0])]
    pairs = ((0, 1), (2, 3), (4, 5), (6, 7), (0, 2), (1, 3), (4, 6), (5, 7), (0, 4), (1, 5), (2, 6), (3, 7))
    return [c[i] for pair in pairs for i in pair]


class Picker:
    """Caches each structure's placed triangles until its transform changes."""

    def __init__(self) -> None:
        self._cache: dict[str, tuple[tuple[Any, ...], Vec, Vec, list[tuple[Vec, Vec, Vec]]]] = {}

    def _triangles(self, st: Structure, model: Model) -> tuple[Vec, Vec, list[tuple[Vec, Vec, Vec]]]:
        key = (st.model, st.x, st.y, st.elevation, st.rotation, st.scale)
        cached = self._cache.get(st.id)
        if cached is None or cached[0] != key:
            m = placement(st)
            tris: list[tuple[Vec, Vec, Vec]] = []
            for part in model.parts:
                v = part.vertices
                pts = [_apply(m, v[i], v[i + 1], v[i + 2]) for i in range(0, len(v), 8)]
                tris += [(pts[part.indices[i]], pts[part.indices[i + 1]], pts[part.indices[i + 2]])
                         for i in range(0, len(part.indices), 3)]
            lo, hi = box(st, model)
            cached = (key, lo, hi, tris)
            self._cache[st.id] = cached
        return cached[1], cached[2], cached[3]

    def pick(self, origin: Vec, direction: Vec, structures: Iterable[Structure], models: dict[str, Model],
             sprites: Iterable[Any] = (), right: Vec = (1.0, 0.0, 0.0), stretch: float = 1.0) -> Hit | None:
        best: Hit | None = None
        for st in structures:
            lo, hi, tris = self._triangles(st, models[st.model])
            if not _slab(origin, direction, best.distance if best else 1e9, lo, hi):
                continue
            for a, b, c in tris:
                t = _hit(origin, direction, a, b, c)
                if t is not None and (best is None or t < best.distance):
                    best = Hit("structure", st.id, t, _along(origin, direction, t))
        for sprite in sprites:
            t = _billboard_hit(origin, direction, sprite, right, stretch)
            if t is not None and (best is None or t < best.distance):
                best = Hit("sprite", sprite, t, _along(origin, direction, t))
        return best


def ground_point(origin: Vec, direction: Vec, height: float = 0.0) -> tuple[float, float] | None:
    """Where the ray meets the horizontal plane z = height (m), or None if it never does."""
    if abs(direction[2]) < 1e-9:
        return None
    t = (height - origin[2]) / direction[2]
    return None if t <= 0 else (origin[0] + direction[0] * t, origin[1] + direction[1] * t)


def _along(o: Vec, d: Vec, t: float) -> Vec:
    return (o[0] + d[0] * t, o[1] + d[1] * t, o[2] + d[2] * t)


def _slab(o: Vec, d: Vec, t_max: float, lo: Vec, hi: Vec) -> bool:
    t0, t1 = 0.0, t_max
    for k in range(3):
        if abs(d[k]) < 1e-12:
            if o[k] < lo[k] or o[k] > hi[k]:
                return False
            continue
        a, b = (lo[k] - o[k]) / d[k], (hi[k] - o[k]) / d[k]
        t0, t1 = max(t0, min(a, b)), min(t1, max(a, b))
        if t0 > t1:
            return False
    return True


def _hit(o: Vec, d: Vec, a: Vec, b: Vec, c: Vec) -> float | None:
    """Moller-Trumbore: the distance along the ray to the triangle, or None."""
    e1 = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    e2 = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    p = (d[1] * e2[2] - d[2] * e2[1], d[2] * e2[0] - d[0] * e2[2], d[0] * e2[1] - d[1] * e2[0])
    det = e1[0] * p[0] + e1[1] * p[1] + e1[2] * p[2]
    if abs(det) < 1e-12:
        return None
    inv = 1.0 / det
    s = (o[0] - a[0], o[1] - a[1], o[2] - a[2])
    u = (s[0] * p[0] + s[1] * p[1] + s[2] * p[2]) * inv
    if u < 0.0 or u > 1.0:
        return None
    q = (s[1] * e1[2] - s[2] * e1[1], s[2] * e1[0] - s[0] * e1[2], s[0] * e1[1] - s[1] * e1[0])
    v = (d[0] * q[0] + d[1] * q[1] + d[2] * q[2]) * inv
    if v < 0.0 or u + v > 1.0:
        return None
    t = (e2[0] * q[0] + e2[1] * q[1] + e2[2] * q[2]) * inv
    return t if t > 1e-6 else None


def _billboard_hit(o: Vec, d: Vec, sprite: Any, right: Vec, stretch: float) -> float | None:
    """The ray against a character's billboard: upright at its feet, facing the camera (as the renderer draws it)."""
    data = getattr(sprite, "mesh_entity_data", None) or {}
    elevation = data.get("elevation", 0.0) if isinstance(data, dict) else 0.0
    x, y = sprite.center_x / PIXELS_PER_METRE, sprite.bottom / PIXELS_PER_METRE
    z = float(elevation or 0.0) / PIXELS_PER_METRE
    half, height = abs(sprite.width) / PIXELS_PER_METRE / 2, abs(sprite.height) / PIXELS_PER_METRE * stretch
    n = (right[1], -right[0], 0.0)  # the quad's normal: horizontal, square to its right vector
    denom = d[0] * n[0] + d[1] * n[1]
    if abs(denom) < 1e-9:
        return None
    t = ((x - o[0]) * n[0] + (y - o[1]) * n[1]) / denom
    if t <= 0:
        return None
    px, py, pz = o[0] + d[0] * t, o[1] + d[1] * t, o[2] + d[2] * t
    across = (px - x) * right[0] + (py - y) * right[1]
    return t if abs(across) <= half and z <= pz <= z + height else None
