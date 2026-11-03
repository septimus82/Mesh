"""#461 R3: a river's bed, its scatter and its water underfoot, headless.

- ``carve_river_bed`` lowers the ground into a channel (deepest in the middle, meeting the water at its edge) with
  walkable banks, deterministic and idempotent, never raising ground, touching nothing else.
- Scatter keeps out of rivers' water; ``clear_scatter_in_rivers`` takes away only what stands in it.
- ``World``: dry ground, shallow water waded (its steps reported), deep water refused, as the water stands over
  the feet. The real window, Studio and Play are tests/test_river_bed_gpu.py."""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any

import pytest

from engine import authoring
from engine import project_ops as ops
from engine.hd2d import river
from engine.hd2d.settings import parse_hd2d
from engine.hd2d.terrain import MAX_SLOPE, Terrain
from engine.hd2d.world import DEEP, World

pytestmark = pytest.mark.fast

P = 32.0
# a 3 m stream flowing east right across a 50 x 37.5 m flat room (edge to edge: no way round it), its water 0.5 m
# below the ground: unseen until its bed is carved
STREAM = [[4.0, 600.0, 96.0, -16.0], [640.0, 620.0, 96.0, -16.0], [1596.0, 600.0, 96.0, -16.0]]


def _scene(points: list[list[float]] = STREAM) -> dict[str, Any]:
    scene = {"entities": [], "settings": {"world_width": 1600, "world_height": 1200,
                                          "hd2d": {"ground": {"texture": "assets/textures/grass.png",
                                                              "from": [0, 0], "to": [1600, 1200]}}}}
    return ops.add_river(scene, "stream", points)


def _terrain(scene: dict[str, Any]) -> Terrain:
    return Terrain.from_ground(parse_hd2d(scene["settings"]["hd2d"]).ground)


def _world(scene: dict[str, Any]) -> World:
    return World(parse_hd2d(scene["settings"]["hd2d"]), {})


def _metres(px: float) -> float:
    return px / P


def test_the_bed_is_deepest_in_the_middle_meets_the_water_at_its_edge_and_its_banks_are_walkable() -> None:
    carved = ops.carve_river_bed(_scene(), "stream")
    t = _terrain(carved)
    level = -16.0  # px
    depth = 0.25 * 3.0 * P  # a quarter of its width: 0.75 m
    # (heights read between the 0.5 m grid's corners: within a corner's worth of the shape)
    assert t.height(640, 620) == pytest.approx(level - depth, abs=1.5), "the middle: its level less its depth"
    assert t.height(640, 620 + 48) == pytest.approx(level, abs=1.5), "at the water's edge the ground meets it"
    assert t.height(640, 620 + 64) == pytest.approx(level + 0.6 * 16, abs=1.5), "a bank rising 0.6 a metre"
    assert t.height(640, 620 + 48 + 6 * P) == 0.0, "past the bank: the ground as it was"
    for y in range(620 + 52, 620 + 48 + 27, 4):  # the bank, up to the ground: every face walkable (no cliff)
        here = t.surface_at(640, y)
        assert here is not None and here[1] >= MAX_SLOPE, (y, here)
    across = [t.height(640, y) or 0.0 for y in range(560, 684, 4)]
    assert all(abs(b - a) < 8.0 for a, b in zip(across, across[1:])), "no seam: a smooth section"


def test_carving_is_deterministic_idempotent_only_lowers_and_keeps_other_ground() -> None:
    scene = ops.sculpt_terrain_stroke(_scene(), "raise", [[1400, 1000, 40]], radius=96)  # a hill far away
    scene = ops.sculpt_terrain_stroke(scene, "lower", [[640, 620, 120]], radius=24)  # a pit already in the bed
    hill_text = json.dumps(scene["settings"]["hd2d"]["ground"]["terrain"]["chunks"].get("2,1"))
    a = ops.carve_river_bed(scene, "stream")
    b = ops.carve_river_bed(copy.deepcopy(scene), "stream")
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True), "the same carve, the same ground"
    with pytest.raises(ops.OpError, match="already carved"):
        ops.carve_river_bed(a, "stream")
    before, after = _terrain(scene), _terrain(a)
    assert all(h1 <= h0 for h0, h1 in zip(before.heights, after.heights)), "ground only ever goes down"
    assert after.height(640, 620) == before.height(640, 620) < -16.0 - 24, "the deeper pit kept"
    assert after.height(1400, 1000) == before.height(1400, 1000) > 30, "the hill untouched"
    assert json.dumps(a["settings"]["hd2d"]["ground"]["terrain"]["chunks"].get("2,1")) == hill_text
    assert a["settings"]["hd2d"]["rivers"] == scene["settings"]["hd2d"]["rivers"], "the river itself unchanged"


def test_depths_vary_along_a_river_a_shallow_point_is_a_ford() -> None:
    points = [[160.0, 600.0, 64.0, -16.0], [640.0, 600.0, 128.0, -16.0], [1120.0, 600.0, 64.0, -16.0]]
    by_width = _terrain(ops.carve_river_bed(_scene(points), "stream"))
    assert by_width.height(640, 600) < by_width.height(200, 600), "wider: deeper (a quarter of its width)"
    ford = _terrain(ops.carve_river_bed(_scene(points), "stream", depths=[0.8, 0.3, 0.8]))
    assert ford.height(640, 600) == pytest.approx(-16.0 - 0.3 * P, abs=1.5)
    assert ford.height(200, 600) == pytest.approx(-16.0 - 0.8 * P, abs=4.0)
    with pytest.raises(ops.OpError, match="one bed depth a point"):
        ops.carve_river_bed(_scene(points), "stream", depths=[0.5])
    with pytest.raises(ops.OpError, match="no river 'brook'"):
        ops.carve_river_bed(_scene(points), "brook")
    with pytest.raises(ops.OpError, match="no river"):
        ops.carve_river_bed({"entities": [], "settings": {}}, "stream")


def test_scatter_keeps_out_of_a_river_and_clearing_takes_only_what_stands_in_its_water() -> None:
    from engine.hd2d.scatter import ASSETS, parse_scatter

    carved = ops.carve_river_bed(_scene(), "stream")
    dabs = [[x, y] for x in range(400, 900, 40) for y in (560, 620, 680)]
    fresh = ops.scatter_stroke(carved, "Meadow", dabs, radius=64, seed=3)
    for name, rows in parse_scatter(fresh["settings"]["hd2d"]["scatter"]).items():
        water = river.RiverIndex(tuple(river.parse_rivers(fresh["settings"]["hd2d"]["rivers"])))
        wet = [r for r in rows if water.level_at(r[0] / P, r[1] / P) and not ASSETS[name].shore]
        assert not wet, (name, wet[:3])  # a stroke over the river puts nothing in its water (reeds apart)
    # what was there before the river: placed with its water ignored, then cleared
    planted = {"grass_tuft": [[600, 620, 0, 100], [600, 700, 0, 100], [1500, 100, 0, 100]],
               "reeds": [[640, 620 - 44, 0, 100]], "rock_small": [[700, 618, 0, 100]]}
    scene = ops.set_scatter(carved, planted)
    scene["entities"].append({"id": "chest", "x": 640.0, "y": 620.0, "name": "Chest"})
    cleared = ops.clear_scatter_in_rivers(scene, "stream")
    kept = parse_scatter(cleared["settings"]["hd2d"]["scatter"])
    assert [600, 620, 0, 100] not in [list(r) for r in kept.get("grass_tuft", [])], "grass in the water: gone"
    assert "rock_small" not in kept, "a rock in the water: gone"
    assert [600, 700, 0, 100] in [list(r) for r in kept["grass_tuft"]] and [1500, 100, 0, 100] in [
        list(r) for r in kept["grass_tuft"]], "on the bank and far away: kept"
    assert kept.get("reeds"), "reeds in the shallows at the edge: kept"
    assert cleared["entities"] == scene["entities"], "objects are never touched"
    with pytest.raises(ops.OpError, match="Nothing scattered stands"):
        ops.clear_scatter_in_rivers(cleared, "stream")
    # editing or removing the river never touches scatter
    assert ops.set_river(cleared, "stream", flow=2.0)["settings"]["hd2d"]["scatter"] == \
        cleared["settings"]["hd2d"]["scatter"]
    assert ops.remove_river(cleared, "stream")["settings"]["hd2d"]["scatter"] == cleared["settings"]["hd2d"]["scatter"]


def test_dry_shallow_and_deep_water_underfoot() -> None:
    world = _world(ops.carve_river_bed(_scene(), "stream"))
    feet = (0.3, 0.19)

    def at(y_px: float) -> tuple[Any, Any]:
        x, y = 20.0, _metres(y_px)
        z = max(h for h, _s in world.heights_at(x, y))
        return world.water_at(x, y, z), world.stand(x, y, z, *feet)

    assert at(800.0) == (None, (0.0, "ground")), "dry ground"
    water, stood = at(620 + 40)  # near the edge: under half a metre of water
    assert water is not None and 0 < water[0] <= DEEP and water[1] == "stream" and stood is not None
    water, stood = at(620)  # the middle: 0.75 m
    assert water is not None and water[0] > DEEP and stood is None, "deep: can't stand there"
    # a character walking in from the bank stops where the water gets too deep
    path = world.path((20.0, _metres(800), 0.0), (20.0, _metres(450), 0.0))
    assert path == [], "no way across: deep all along"


def test_a_ford_can_be_walked_across_and_the_navigation_grid_knows_it() -> None:
    # edge to edge across the room (no way round its ends), shallow at its middle point (x 800 px)
    points = [[4.0, 600.0, 96.0, -16.0], [800.0, 600.0, 96.0, -16.0], [1596.0, 600.0, 96.0, -16.0]]
    world = _world(ops.carve_river_bed(_scene(points), "stream", depths=[1.0, 0.25, 1.0]))
    route = world.path((_metres(800), _metres(800), 0.0), (_metres(800), _metres(400), 0.0))
    assert route, "across at the ford"
    deepest = max(w[0] for p in route if (w := world.water_at(p[0], p[1], p[2])) is not None)
    assert deepest <= DEEP, deepest
    far = world.path((_metres(200), _metres(800), 0.0), (_metres(200), _metres(400), 0.0))
    assert far, "from upstream too: by the ford"
    assert all(w is None or w[0] <= DEEP for p in far for w in [world.water_at(p[0], p[1], p[2])])
    bed = min(h for h, _s in world.heights_at(_metres(200), _metres(600)))
    assert world.stand(_metres(200), _metres(600), bed, 0.3, 0.19) is None, "mid-stream upstream: deep"


def test_wading_steps_are_reported_dry_ground_and_deep_water_none() -> None:
    from types import SimpleNamespace

    points = [[p[0], p[1], p[2], 3.2] for p in STREAM]
    scene = _scene(points)  # its water 0.1 m over flat ground (not carved: proud of it), waded everywhere
    world = _world(scene)
    steps: list[tuple[Any, ...]] = []
    world.on_wade = lambda sprite, feet, rid: steps.append((feet, rid))
    sprite = SimpleNamespace(center_x=640.0, center_y=640.0, bottom=620.0, mesh_entity_data={"elevation": 0.0})
    for _ in range(40):  # 40 moves of 2 px east, through the water: a step every 14 px
        sprite.center_x += 2.0
        world._wade(sprite)
    assert len(steps) == 6 and all(rid == "stream" for _f, rid in steps), steps
    assert sprite.mesh_hd2d_wading is not None and sprite.mesh_hd2d_wading[0] == pytest.approx(0.1, abs=0.01)
    sprite.center_y, sprite.bottom = 900.0, 880.0
    world._wade(sprite)
    assert sprite.mesh_hd2d_wading is None and len(steps) == 6, "dry: no step"


def test_rooms_without_rivers_are_as_they_were() -> None:
    plain = {"ground": {"texture": "assets/textures/grass.png", "from": [0, 0], "to": [1600, 1200]}}
    world = World(parse_hd2d(plain), {})
    assert not world.rivers and world.water_at(20.0, 19.0, 0.0) is None
    assert world.stand(20.0, 19.0, 0.0, 0.3, 0.19) == (0.0, "ground")


def test_ai_carves_and_clears_and_reviews_it_saved_and_undone(tmp_path: Path) -> None:
    from engine.project_scaffold import create_project
    from engine.studio_project import Project

    assert {"carve_river_bed", "clear_scatter_in_rivers"} <= set(authoring.operations())
    root = tmp_path / "game"
    create_project(root, "Game", template_id="hd2d_rpg")
    world_file = json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"]
    project = Project(root, world_file)
    room = project.current
    authoring.apply(project, [{"op": "add_river", "room": room, "river_id": "brook",
                               "points": [[150, 110, 64, 0], [300, 80, 64, -2], [560, 90, 72, -4]]}])
    before = project.scene(room)
    undo0 = len(project._undo)
    authoring.apply(project, [{"op": "carve_river_bed", "room": room, "river_id": "brook"}])
    carved = project.scene(room)
    assert len(project._undo) == undo0 + 1, "one undo step"
    lines = authoring.summarize({"rooms": {room: before}}, {"rooms": {room: carved}})
    assert any("ground" in line.lower() or "terrain" in line.lower() for line in lines), lines
    project.save()
    reopened = Project(root, world_file).scene(room)
    assert reopened["settings"]["hd2d"]["ground"] == carved["settings"]["hd2d"]["ground"], "saved, reopened: same"
    project.undo()
    assert project.scene(room)["settings"]["hd2d"]["ground"] == before["settings"]["hd2d"]["ground"], "undone"
    # rebuilt from what was saved: the same bed, corner for corner
    again = ops.carve_river_bed(before, "brook")
    assert again["settings"]["hd2d"]["ground"] == carved["settings"]["hd2d"]["ground"]
    assert math.isclose(len(json.dumps(again)), len(json.dumps(carved)))
