"""Milestone 12.2: shadows shaped like what casts them, and no light or shadow where it can't be.

* A round tile on the walls layer (a rock, a bush, a tree) casts the outline of its picture, not its whole square;
  solid wall tiles still cast as merged rectangles; water casts nothing.
* One wall painted as an L is two rectangles to the loader: neither may shadow the other's face (a half-shadowed
  wall tile at the joint).
* A soft lamp beside a wall: the lamp's sample points inside the wall are not light sources (they leaked wedges of
  light behind the wall), and the rest carry the whole shadow.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.lighting.light_compositor import _lamp_points
from engine.lighting.occluders import Rect, _tileset_shapes, build_occluders_from_scene_payload
from engine.lighting.shadows import _inside_polygon, light_shadow_polygons

pytestmark = pytest.mark.fast

REPO = Path(__file__).resolve().parents[1]
STARTER = REPO / "assets" / "tilesets" / "starter.json"
WALL, ROCK, BUSH, WATER = 9, 13, 14, 16  # starter gids


def test_see_through_wall_tiles_cast_their_outline_and_water_casts_none() -> None:
    shapes = _tileset_shapes(STARTER.resolve())
    for gid in (ROCK, BUSH):
        outline = shapes[gid - 1]
        assert outline is not None and 6 <= len(outline) <= 12, outline
        xs, ys = [p[0] for p in outline], [p[1] for p in outline]
        assert min(xs) >= 0 and max(xs) <= 32 and min(ys) >= 0 and max(ys) <= 32
        assert (max(xs) - min(xs)) * (max(ys) - min(ys)) < 0.8 * 32 * 32, "smaller than the whole tile"
    assert WALL - 1 not in shapes, "a solid wall tile casts as the whole tile"
    assert shapes[WATER - 1] is None, "water casts no shadow"


def _scene_on_disk(tmp_path: Path, tiles: dict[tuple[int, int], int]) -> tuple[dict, str]:
    maps, scenes = tmp_path / "maps", tmp_path / "scenes"
    maps.mkdir()
    scenes.mkdir()
    (maps / "room.json").write_text(json.dumps({"tilesets": [{"firstgid": 1, "source": str(STARTER)}]}), encoding="utf-8")
    data = [0] * (10 * 8)
    for (col, row), gid in tiles.items():
        data[row * 10 + col] = gid
    scene = {"tilemap": {"path": "../maps/room.json", "width": 10, "height": 8, "tilewidth": 32, "tileheight": 32,
                         "collision_layer_id": "walls", "tile_layers": [{"id": "walls", "tiles": data}]}}
    return scene, str(scenes / "room.json")


def test_a_rock_tile_is_an_outline_and_solid_walls_still_merge(tmp_path: Path) -> None:
    from engine.lighting.occluders import OCCLUDER_CACHE

    OCCLUDER_CACHE.invalidate()
    scene, path = _scene_on_disk(tmp_path, {(2, 3): ROCK, (5, 1): WALL, (6, 1): WALL, (7, 6): WATER})
    occluders = build_occluders_from_scene_payload(scene, scene_path=path, revision=1)
    polys = [o for o in occluders if o["type"] == "poly"]
    rects = [o for o in occluders if o["type"] == "rect"]
    assert len(polys) == 1 and all(64 <= x <= 96 and 128 <= y <= 160 for x, y in polys[0]["points"]), polys
    assert rects == [{"id": "auto_walls_160_192_64_32", "type": "rect", "x": 160.0, "y": 192.0, "width": 64.0, "height": 32.0}]
    OCCLUDER_CACHE.invalidate()
    (tmp_path / "other").mkdir()
    unknown, _ = _scene_on_disk(tmp_path / "other", {(2, 3): ROCK})
    plain = build_occluders_from_scene_payload(unknown, scene_path="nowhere/room.json", revision=2)
    assert [o["type"] for o in plain] == ["rect"], "no map file found: every tile casts as the whole tile, as before"
    OCCLUDER_CACHE.invalidate()


def _points_inside(rect: Rect) -> list[tuple[float, float]]:
    return [(rect.x + rect.width * fx, rect.y + rect.height * fy) for fx in (0.2, 0.5, 0.8) for fy in (0.2, 0.5, 0.8)]


@pytest.mark.parametrize("light", [(470.0, 250.0), (200.0, 200.0), (230.0, 420.0), (360.0, 330.0)])
def test_a_wall_painted_as_an_l_never_shadows_its_own_face(light: tuple[float, float]) -> None:
    # As the loader merges an L of tiles: a vertical strip on top of a horizontal one.
    arm, foot = Rect(288.0, 288.0, 32.0, 96.0), Rect(288.0, 256.0, 128.0, 32.0)
    pillar = Rect(150.0, 300.0, 32.0, 32.0)  # a separate wall: another wall's shadow does reach it
    shadows = light_shadow_polygons(light, 260.0, [arm, foot, pillar], [])
    for rect in (arm, foot):
        for pt in _points_inside(rect):
            assert not any(_inside_polygon(pt[0], pt[1], s) for s in shadows), (light, rect, pt)


def test_another_walls_shadow_still_falls_on_a_wall() -> None:
    wall, pillar_behind = Rect(300.0, 200.0, 32.0, 120.0), Rect(400.0, 240.0, 32.0, 32.0)
    shadows = light_shadow_polygons((200.0, 256.0), 300.0, [wall, pillar_behind], [])
    assert any(_inside_polygon(416.0, 256.0, s) for s in shadows), "a pillar behind a wall stays in its shadow"


def test_a_soft_lamps_points_inside_a_wall_are_not_light_sources() -> None:
    wall = Rect(280.0, 276.0, 160.0, 24.0)
    points = _lamp_points(318.0, 262.0, 22.0, 16, [wall], [])
    assert 0 < len(points) < 16
    assert all(not (wall.x < 318.0 + dx < wall.x + wall.width and wall.y < 262.0 + dy < wall.y + wall.height) for dx, dy in points)
    assert _lamp_points(318.0, 262.0, 0.0, 1, [wall], []) == [(0.0, 0.0)], "a point lamp is unchanged"
    assert len(_lamp_points(100.0, 100.0, 22.0, 16, [wall], [])) == 16, "away from walls: every point"
