"""Milestone 22A.1: a flat HD-2D room's ground grown east and north (``project_ops.expand_hd2d_room``). Headless; its
map file kept at the room's size when Studio saves: tests/test_hd2d_room_expand_save.py."""

from __future__ import annotations

import base64
import copy
import struct

import pytest

import engine.project_ops as ops
from engine.hd2d.scatter import ASSETS
from engine.hd2d.settings import parse_hd2d

pytestmark = pytest.mark.fast

PATH = "packs/core_regions/scenes/meadow.json"


def _room(width: float = 40, depth: float = 30) -> dict:
    scene, _map_path, _skeleton = ops.make_hd2d_room({"name": "Meadow", "entities": []}, PATH, width, depth)
    return scene


def _populated() -> dict:
    """A room with something of everything: a structure, people, water, a sound, a light, scatter, painted tiles."""
    scene = _room()
    scene, _structure = ops.place_structure(scene, "assets/hd2d_starter/models/cottage.glb", 640.0, 480.0)
    scene, _npc = ops.paste_entity(scene, "meadow", {"name": "Elder", "x": 0, "y": 0}, 1200.0, 900.0)
    scene, pond = ops.paste_entity(scene, "meadow", {"name": "Pond", "x": 0, "y": 0}, 300.0, 200.0)
    scene = ops.set_water(scene, pond, preset="natural_pond")
    scene, brook = ops.paste_entity(scene, "meadow", {"name": "Brook", "x": 0, "y": 0}, 320.0, 220.0)
    scene = ops.set_sound_emitter(scene, brook, volume=0.5, radius=96, distance=320)
    scene, _light = ops.add_light(scene, 1260.0, 940.0)
    scene["settings"]["hd2d"]["scatter"] = {next(iter(ASSETS)): [[400, 300, 0, 100], [1270, 950, 90, 120]]}
    walls = next(layer for layer in scene["tilemap"]["tile_layers"] if layer["id"] == ops.WALLS)
    walls["tiles"][0] = walls["tiles"][-1] = ops.STARTER_WALL  # the top-left and bottom-right tiles
    ground = next(layer for layer in scene["tilemap"]["tile_layers"] if layer["id"] == ops.GROUND)
    ground["tiles"][5 * 40 + 5] = ops.STARTER_FLOOR  # a path tile among the grass
    return scene


def _without_size(scene: dict) -> dict:
    out = copy.deepcopy(scene)
    out.pop("tilemap")
    for key in ("world_width", "world_height"):
        out["settings"].pop(key)
    out["settings"]["hd2d"]["ground"].pop("to")
    out["settings"]["hd2d"]["camera"].pop("bounds", None)
    return out


def _cells(scene: dict, layer_id: str) -> dict[tuple[float, float], int]:
    """Each tile by its world position (its centre, px): what a resize must keep."""
    info = ops.map_info(scene)
    tiles = info["layers"][layer_id]
    return {ops.cell_center(info, i % info["width"], i // info["width"]): t for i, t in enumerate(tiles)}


def test_a_populated_room_grows_east_and_north_with_everything_where_it_was() -> None:
    before = _populated()
    after = ops.expand_hd2d_room(before, 48, 36)
    assert _without_size(after) == _without_size(before)  # structures, people, water, sound, light, scatter, sun...
    settings = after["settings"]
    assert settings["hd2d"]["ground"]["from"] == [0, 0] and settings["hd2d"]["ground"]["to"] == [1536.0, 1152.0]
    assert settings["hd2d"]["camera"]["bounds"] == [0.0, 0.0, 1536.0, 1152.0]  # the room's edges: grown with it
    assert (settings["world_width"], settings["world_height"]) == (1536.0, 1152.0)
    assert (after["tilemap"]["width"], after["tilemap"]["height"]) == (48, 36)
    for layer_id in (ops.GROUND, ops.WALLS, ops.OVERHEAD):  # every tile painted before is where it was
        old, new = _cells(before, layer_id), _cells(after, layer_id)
        assert all(new[at] == tile for at, tile in old.items()), layer_id
    new_ground = [t for at, t in _cells(after, ops.GROUND).items() if at not in _cells(before, ops.GROUND)]
    assert len(new_ground) == 48 * 36 - 40 * 30 and set(new_ground) == {ops.STARTER_GRASS}  # the room's ground tile
    new_walls = [t for at, t in _cells(after, ops.WALLS).items() if at not in _cells(before, ops.WALLS)]
    assert set(new_walls) == {0}  # nothing built in the new ground
    parsed = parse_hd2d(settings["hd2d"], map_size_px=(1536.0, 1152.0))
    assert parsed.ground.hi == (1536.0, 1152.0) and parsed.ground.terrain is None


def test_one_side_grows_alone_and_custom_or_no_bounds_are_kept() -> None:
    wider = ops.expand_hd2d_room(_room(), 50, 30)
    assert wider["tilemap"]["height"] == 30 and wider["settings"]["hd2d"]["ground"]["to"] == [1600.0, 960.0]
    framed = _room()
    framed["settings"]["hd2d"]["camera"]["bounds"] = [100.0, 100.0, 900.0, 700.0]  # set by hand: a framed part
    assert ops.expand_hd2d_room(framed, 48, 36)["settings"]["hd2d"]["camera"]["bounds"] == [100.0, 100.0, 900.0, 700.0]
    loose = ops.set_hd2d_camera(_room(), bounded=False)
    assert "bounds" not in ops.expand_hd2d_room(loose, 48, 36)["settings"]["hd2d"]["camera"]
    bounded = ops.set_hd2d_camera(ops.expand_hd2d_room(loose, 48, 36), bounded=True)  # back on: the new edges
    assert bounded["settings"]["hd2d"]["camera"]["bounds"] == [0.0, 0.0, 1536.0, 960.0 * 36 / 30]


@pytest.mark.parametrize(("width", "depth", "reason"), [
    (39, 30, "can only grow .*shrinking isn't supported"),
    (40, 29, "depth can only grow"),
    (40, 30, "already 40 x 30 m"),
    (300, 30, "8 to 256"),
    (40.5, 30, "whole number of metres"),
    ("wide", 30, "whole number of metres"),
    (True, 30, "whole number of metres"),
])
def test_odd_sizes_are_refused_with_the_reason(width: object, depth: object, reason: str) -> None:
    with pytest.raises(ops.OpError, match=reason):
        ops.expand_hd2d_room(_room(), width, depth)


def test_unsupported_rooms_are_refused_with_the_reason() -> None:
    from engine.hd2d.terrain import CHUNK

    sculpted = _room()  # one chunk of heights raised 1 px
    raised = base64.b64encode(struct.pack(f"<{CHUNK * CHUNK}h", *[4] * (CHUNK * CHUNK))).decode()
    sculpted["settings"]["hd2d"]["ground"]["terrain"] = {"cell": 16, "chunks": {"0,0": raised}}
    painted = _room()
    painted["settings"]["hd2d"]["ground"]["terrain"] = {"cell": 16, "chunks": {}, "edges": "hard"}
    shifted = _room()
    shifted["settings"]["hd2d"]["ground"]["from"] = [64, 0]
    no_ground = _room()
    no_ground["settings"]["hd2d"].pop("ground")
    map_off = _room()
    map_off = ops.resize_map(map_off, 30, 30)
    world_off = _room()
    world_off["settings"]["world_width"] = 2000.0
    half_metre = _room()
    half_metre["settings"]["hd2d"]["ground"]["to"] = [1296.0, 960.0]
    for scene, reason in ((sculpted, "sculpted or painted"), (painted, "sculpted or painted"), (shifted, "not at the room's south-west corner"),
                          (no_ground, "no HD-2D ground"), (map_off, "map \\(30 x 30 tiles\\) doesn't match"),
                          (world_off, "world size .* doesn't match"), (half_metre, "isn't whole metres"),
                          ({"name": "R", "entities": [], "settings": {}}, "isn't an HD-2D room")):
        with pytest.raises(ops.OpError, match=reason):
            ops.expand_hd2d_room(scene, 48, 36)
        size = ops.hd2d_room_size(scene)
        assert not size["expandable"] and reason.split(" ")[0].strip("\\(") in size["why"]
    assert ops.hd2d_room_size(_room()) == {"width": 40, "depth": 30, "expandable": True, "why": None}


def test_a_2d_rooms_resize_is_unchanged() -> None:
    scene, _path, _skeleton = ops.add_map({"name": "R", "entities": []}, PATH, width=20, height=15,
                                          ground=ops.STARTER_FLOOR, border=ops.STARTER_WALL)
    grown = ops.resize_map(scene, 24, 18)
    ground = grown["tilemap"]["tile_layers"][0]["tiles"]
    assert ground.count(0) == 24 * 18 - 20 * 15  # 2D Resize: new tiles empty, as before M22A.1


def test_new_ground_continues_the_edge_it_grows_from_not_the_most_common_tile() -> None:
    """A grass-bordered room with a larger paved middle: the most common tile is the paving, the new ground is grass."""
    scene = _room(10, 10)
    ground = next(layer for layer in scene["tilemap"]["tile_layers"] if layer["id"] == ops.GROUND)
    for i in range(100):
        if i % 10 not in (0, 9) and i // 10 not in (0, 9):
            ground["tiles"][i] = ops.STARTER_FLOOR
    assert ground["tiles"].count(ops.STARTER_FLOOR) > ground["tiles"].count(ops.STARTER_GRASS)
    after = ops.expand_hd2d_room(scene, 12, 12)
    old, new = _cells(scene, ops.GROUND), _cells(after, ops.GROUND)
    assert all(new[at] == tile for at, tile in old.items())  # the paving and the border where they were
    assert {tile for at, tile in new.items() if at not in old} == {ops.STARTER_GRASS}


def test_a_mixed_edge_is_refused_not_guessed_and_the_other_way_still_grows() -> None:
    scene = _room(10, 10)
    ground = next(layer for layer in scene["tilemap"]["tile_layers"] if layer["id"] == ops.GROUND)
    ground["tiles"][5 * 10 + 9] = ops.STARTER_FLOOR  # a path running off the east edge
    before = copy.deepcopy(scene)
    with pytest.raises(ops.OpError, match=r"east edge aren't all one tile \(tile 1: 9, tile 5: 1\).*nothing was"):
        ops.expand_hd2d_room(scene, 12, 10)
    with pytest.raises(ops.OpError, match=r"east and north edges aren't all one tile \(tile 1: 19, tile 5: 1\)"):
        ops.expand_hd2d_room(scene, 12, 12)
    assert scene == before
    north = ops.expand_hd2d_room(scene, 10, 12)  # its north edge is all grass
    assert {t for at, t in _cells(north, ops.GROUND).items() if at not in _cells(scene, ops.GROUND)} == {ops.STARTER_GRASS}
