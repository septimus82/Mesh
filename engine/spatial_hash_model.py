"""Deterministic spatial hash model for broad-phase queries."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable, Sequence, Tuple, TypeVar

from .physics_model import Aabb


@dataclass(frozen=True, slots=True)
class SpatialHashConfig:
    cell_size_px: int


@dataclass(frozen=True, slots=True)
class SpatialHashIndex:
    cfg: SpatialHashConfig
    cells: dict[tuple[int, int], tuple[int, ...]]
    item_count: int


def _cell_index(value: float, cell_size: int) -> int:
    return int(math.floor(value / float(cell_size)))


def spatial_hash_cells_for_aabb(aabb: Aabb, cfg: SpatialHashConfig) -> tuple[tuple[int, int], ...]:
    size = int(cfg.cell_size_px)
    if size <= 0:
        return ()
    left = float(aabb.left)
    right = float(aabb.right)
    bottom = float(aabb.bottom)
    top = float(aabb.top)
    if right <= left:
        right = left + 1e-9
    if top <= bottom:
        top = bottom + 1e-9
    min_ix = _cell_index(left, size)
    max_ix = _cell_index(right - 1e-9, size)
    min_iy = _cell_index(bottom, size)
    max_iy = _cell_index(top - 1e-9, size)
    cells: list[tuple[int, int]] = []
    for ix in range(min_ix, max_ix + 1):
        for iy in range(min_iy, max_iy + 1):
            cells.append((ix, iy))
    cells.sort()
    return tuple(cells)


T = TypeVar("T")


def build_spatial_hash(
    items: Sequence[T],
    get_aabb: Callable[[T], Aabb],
    cfg: SpatialHashConfig,
) -> SpatialHashIndex:
    cells: dict[tuple[int, int], list[int]] = {}
    for idx, item in enumerate(items):
        aabb = get_aabb(item)
        for cell in spatial_hash_cells_for_aabb(aabb, cfg):
            bucket = cells.setdefault(cell, [])
            bucket.append(idx)
    frozen: dict[tuple[int, int], tuple[int, ...]] = {}
    for key in sorted(cells.keys()):
        bucket = cells[key]
        frozen[key] = tuple(bucket)
    return SpatialHashIndex(cfg=cfg, cells=frozen, item_count=len(items))


def query_aabb(index: SpatialHashIndex, aabb: Aabb) -> list[int]:
    cells = spatial_hash_cells_for_aabb(aabb, index.cfg)
    if not cells:
        return []
    found: set[int] = set()
    for cell in cells:
        for item_id in index.cells.get(cell, ()):
            found.add(int(item_id))
    return sorted(found)


def query_point(index: SpatialHashIndex, x: float, y: float) -> list[int]:
    size = int(index.cfg.cell_size_px)
    if size <= 0:
        return []
    cell = (_cell_index(float(x), size), _cell_index(float(y), size))
    items = index.cells.get(cell, ())
    return sorted(set(int(i) for i in items))
