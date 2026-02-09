from __future__ import annotations

from engine.physics_model import Aabb
from engine.spatial_hash_model import (
    SpatialHashConfig,
    build_spatial_hash,
    query_aabb,
    query_point,
    spatial_hash_cells_for_aabb,
)


def test_cells_for_aabb_deterministic() -> None:
    cfg = SpatialHashConfig(cell_size_px=10)
    aabb = Aabb(5, 5, 10, 10)
    cells1 = spatial_hash_cells_for_aabb(aabb, cfg)
    cells2 = spatial_hash_cells_for_aabb(aabb, cfg)
    assert cells1 == cells2
    assert cells1 == ((0, 0),)


def test_cells_for_aabb_negative_coords() -> None:
    cfg = SpatialHashConfig(cell_size_px=10)
    aabb = Aabb(-5, -5, 10, 10)
    cells = spatial_hash_cells_for_aabb(aabb, cfg)
    assert cells == ((-1, -1),)


def test_build_and_query_deterministic() -> None:
    cfg = SpatialHashConfig(cell_size_px=10)
    items = [Aabb(5, 5, 10, 10), Aabb(25, 5, 10, 10)]
    index = build_spatial_hash(items, lambda a: a, cfg)
    ids = query_aabb(index, Aabb(5, 5, 10, 10))
    assert ids == [0]
    ids2 = query_aabb(index, Aabb(25, 5, 10, 10))
    assert ids2 == [1]


def test_query_point_sorted_unique() -> None:
    cfg = SpatialHashConfig(cell_size_px=10)
    items = [Aabb(5, 5, 10, 10), Aabb(6, 6, 10, 10)]
    index = build_spatial_hash(items, lambda a: a, cfg)
    ids = query_point(index, 5, 5)
    assert ids == [0, 1]


def test_empty_index() -> None:
    cfg = SpatialHashConfig(cell_size_px=10)
    index = build_spatial_hash([], lambda a: a, cfg)
    ids = query_aabb(index, Aabb(0, 0, 1, 1))
    assert ids == []
