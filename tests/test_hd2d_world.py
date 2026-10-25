"""Milestone 16 Stage 3: floors, stairs and bridges. Collision authored in Blender (``mesh_collision`` node extras in
tooling/hd2d_assets/stone_crossing.glb) becomes a world where one rule decides where a character can stand; moving,
NPC paths and saves use it. Headless: no window."""

from __future__ import annotations

import json
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine.hd2d.glb import GlbError, load_glb
from engine.hd2d.settings import Hd2dSettingsError, parse_hd2d
from engine.hd2d.world import World

pytestmark = pytest.mark.fast

REPO = Path(__file__).resolve().parents[1]
CROSSING = REPO / "tooling" / "hd2d_assets" / "stone_crossing.glb"
FEET = (0.3, 0.19)  # half a character's feet box (m)


@pytest.fixture(scope="module")
def world() -> World:
    settings = parse_hd2d({"structures": [{"id": "crossing", "model": "c.glb", "x": 512, "y": 384}],
                           "ground": {"to": [1024, 768]}})
    return World(settings, {"c.glb": load_glb(CROSSING)})


def test_collision_comes_from_the_blender_extras_and_is_never_drawn() -> None:
    model = load_glb(CROSSING)
    kinds = {c.node: c.kind for c in model.colliders}
    assert kinds["col_bridge_deck"] == "floor" and kinds["col_platform_west"] == "solid"
    assert kinds["col_stairs_east"] == "solid" and kinds["col_railing_north"] == "wall" and kinds["col_hut"] == "wall"
    assert not any(p.node.startswith("col_") for p in model.parts), "collision nodes aren't rendered"
    deck = next(c for c in model.colliders if c.node == "col_bridge_deck")
    assert len(deck.triangles) == 2 and all(p[2] == pytest.approx(2.0) for t in deck.triangles for p in t), "its top"


@pytest.mark.parametrize(("where", "at", "expected"), [
    ("on the ground", (16, 3, 0), (0.0, "ground")),
    ("under the bridge", (16, 12, 0), (0.0, "ground")),
    ("on the bridge, over the same spot", (16, 12, 2), (2.0, "crossing/col_bridge_deck")),
    ("half way up the stairs", (10, 6.5, 1.0), (1.0, "crossing/col_stairs_west")),
    ("on a platform", (10, 12, 2), (2.0, "crossing/col_platform_west")),
    ("inside a platform, from the ground", (10, 12, 0), None),
    ("beside the stairs at their middle, from the ground", (8.8, 6.5, 0), None),
    ("off a platform's edge", (6.9, 12, 2), None),
    ("against the bridge railing", (16, 12.8, 2), None),
    ("inside the hut", (22, 13.5, 2), None),
])
def test_one_rule_decides_where_a_character_can_stand(world: World, where: str, at: tuple, expected: tuple | None) -> None:
    got = world.stand(*at, *FEET)
    assert (got if got is None else (pytest.approx(got[0], abs=1e-3), got[1])) == expected, where


def _walker(x_m: float, y_m: float, elevation_m: float = 0.0) -> SimpleNamespace:
    """A sprite-like character: 32 x 48 px, its feet box the bottom quarter (as the player's)."""
    return SimpleNamespace(center_x=x_m * 32, center_y=y_m * 32 + 18, width=32.0, height=48.0, scale_x=1.0,
                           mesh_entity_data={"elevation": elevation_m * 32,
                                             "components": {"collider": {"kind": "box", "auto": True}}})


def _walk(world: World, sprite: SimpleNamespace, dx: float, dy: float, frames: int) -> None:
    for _ in range(frames):
        world.move(sprite, (dx, dy), [])


def test_moving_up_the_stairs_onto_the_platform_and_across_the_bridge(world: World) -> None:
    hero = _walker(10, 3)
    _walk(world, hero, 0, 2.5, 110)  # north: up the west stairs (2.5 px a frame, as the player walks)
    assert hero.mesh_entity_data["elevation"] == pytest.approx(64.0) and hero.mesh_hd2d_floor.endswith("platform_west")
    _walk(world, hero, 2.5, 0, 200)  # east over the bridge
    assert hero.mesh_entity_data["elevation"] == pytest.approx(64.0)
    assert hero.center_x / 32 > 19, "crossed onto the east platform"


def test_ledges_and_walls_stop_movement_but_the_underpass_is_open(world: World) -> None:
    under = _walker(16, 3)
    _walk(world, under, 0, 2.5, 160)  # north, under the bridge
    assert under.mesh_entity_data["elevation"] == 0.0 and under.center_y / 32 > 15, "walked under the deck"
    side = _walker(16, 12)
    _walk(world, side, 2.5, 0, 80)  # east into the platform's side
    assert side.center_x / 32 == pytest.approx(19 - 0.3, abs=0.1)
    edge = _walker(10, 12, 2.0)
    _walk(world, edge, -2.5, 0, 80)  # west, off the platform: no falling
    assert edge.center_x / 32 == pytest.approx(7 + 0.0, abs=0.1) and edge.mesh_entity_data["elevation"] == 64.0


def test_npc_paths_use_the_stairs_and_not_the_ledges(world: World) -> None:
    route = world.path((16.0, 3.0, 0.0), (24.0, 11.0, 2.0))  # ground -> east platform
    assert route and route[-1] == (24.0, 11.0, 2.0)
    climbing = [p for p in route if 0.3 < p[2] < 1.7]
    assert climbing and all(21 <= p[0] <= 23 and 4.4 <= p[1] <= 8.6 for p in climbing), "up the east stairs only"
    assert all(abs(b[2] - a[2]) <= 0.35 for a, b in zip(route, route[1:])), "never a jump"
    assert world.path((16.0, 3.0, 0.0), (22.0, 13.5, 2.0)) == [], "inside the hut: no way there"


def test_structure_ids_are_stable_and_unique() -> None:
    assert parse_hd2d({"structures": [{"model": "a.glb"}]}).structures[0].id == "structure0"
    with pytest.raises(Hd2dSettingsError, match="used twice"):
        parse_hd2d({"structures": [{"id": "a", "model": "a.glb"}, {"id": "a", "model": "b.glb"}]})
    with pytest.raises(Hd2dSettingsError, match=r"structures\[0\] has unknown keys: floors"):
        parse_hd2d({"structures": [{"model": "a.glb", "floors": 2}]})


def test_a_bad_collision_kind_is_refused(tmp_path: Path) -> None:
    pos = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 0, -1)
    doc = {"asset": {"version": "2.0"}, "scenes": [{"nodes": [0, 1]}],
           "nodes": [{"name": "art", "mesh": 0}, {"name": "col_x", "mesh": 0, "extras": {"mesh_collision": "lava"}}],
           "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
           "buffers": [{"byteLength": len(pos)}], "bufferViews": [{"buffer": 0, "byteLength": len(pos)}],
           "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3"}]}
    js = json.dumps(doc).encode()
    js += b" " * (-len(js) % 4)
    body = struct.pack("<I4s", len(js), b"JSON") + js + struct.pack("<I4s", len(pos), b"BIN\0") + pos
    (tmp_path / "bad.glb").write_bytes(b"glTF" + struct.pack("<II", 2, 12 + len(body)) + body)
    with pytest.raises(GlbError, match="col_x': mesh_collision must be one of solid, floor, wall"):
        load_glb(tmp_path / "bad.glb")


def test_elevation_is_saved_as_it_changes_and_2d_rooms_have_no_floor_movement() -> None:
    from engine.behaviours.floor_route import FloorRouteBehaviour
    from engine.scene_runtime.persistence import _SPRITE_SYNC_ENTITY_FIELDS

    assert "elevation" in _SPRITE_SYNC_ENTITY_FIELDS, "a climbed character is saved on its floor"
    npc = _walker(5, 5)
    route = FloorRouteBehaviour(npc, SimpleNamespace(hd2d_world=None), route=[[0, 0, 0], [64, 64, 0]])
    route.update(1 / 60)
    assert (npc.center_x, npc.center_y) == (160.0, 178.0), "no HD-2D floors: FloorRoute does nothing"
