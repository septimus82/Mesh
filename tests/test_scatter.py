"""Milestone 20D: scattered decoration, headless: its storage (explicit, sorted, never regenerated), the brush (density,
spacing, clumps, the rules: slope, material, water, structures; thin and remove), the checked edits Studio, the CLI and
AI share, collision (only what blocks blocks, standing on the ground as it is now) and what is said when something
stands in the way. The drawing is tests/test_terrain_gpu.py."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

from engine import authoring
from engine import project_ops as ops
from engine.hd2d.scatter import ASSETS, MAX_INSTANCES, Scatter, parse_scatter, stored
from engine.hd2d.settings import Hd2dSettingsError, parse_hd2d
from engine.hd2d.terrain import Terrain
from engine.hd2d.world import World

pytestmark = pytest.mark.fast
PX = 32.0


def _room(size: tuple[int, int] = (1024, 768)) -> dict[str, Any]:
    return {"entities": [], "settings": {"world_width": size[0], "world_height": size[1],
                                         "hd2d": {"ground": {"from": [0, 0], "to": list(size)}}}}


def _rows(room: dict[str, Any]) -> dict[str, list[list[int]]]:
    return room["settings"]["hd2d"].get("scatter", {})


def _all(room: dict[str, Any]) -> list[tuple[str, list[int]]]:
    return [(a, r) for a, rows in _rows(room).items() for r in rows]


def _line(y: float = 384.0) -> list[list[float]]:
    return [[96.0 + 16 * k, y] for k in range(52)]


def test_scatter_is_stored_explicitly_sorted_and_the_same_every_time() -> None:
    a = ops.scatter_stroke(_room(), "Meadow", _line(), 64, seed=4)
    assert a == ops.scatter_stroke(_room(), "Meadow", _line(), 64, seed=4), "the same stroke, the same scatter"
    assert a != ops.scatter_stroke(_room(), "Meadow", _line(), 64, seed=5), "the seed decides where"
    rows = _rows(a)
    assert list(rows) == [n for n in ASSETS if n in rows], "assets in a fixed order"
    for items in rows.values():
        assert items == sorted(items, key=lambda r: (r[1], r[0], r[2], r[3]))
        assert all(len(r) == 4 and all(type(v) is int for v in r) for r in items)
    assert stored(parse_scatter(rows)) == rows, "read and written again: the same text"
    assert set(rows) <= {"grass_tuft", "grass_tall", "flowers_yellow", "flowers_pink"}


def test_density_spacing_and_clumps() -> None:
    room = ops.scatter_stroke(_room(), {"grass_tuft": 1}, [[512, 384]], 160, density=2.0, clumping=0.0, seed=1)
    n = len(_all(room))
    expected = 2.0 * math.pi * (160 / PX) ** 2
    assert 0.85 * expected <= n <= expected + 1, (n, expected)
    pts = [r for _a, r in _all(room)]
    nearest = min(math.dist(p[:2], q[:2]) for i, p in enumerate(pts) for q in pts[i + 1:])
    assert nearest >= ASSETS["grass_tuft"].spacing * PX - 1
    again = ops.scatter_stroke(room, {"grass_tuft": 1}, [[512, 384]] * 5, 160, density=2.0, clumping=0.0, seed=2)
    assert len(_all(again)) == n, "filled to the density: going over it again adds nothing"
    clumped = ops.scatter_stroke(_room(), {"grass_tuft": 1}, [[512, 384]], 160, density=2.0, clumping=1.0, seed=1)
    assert len(_all(clumped)) <= n, "clumps leave gaps"


def test_rules_keep_scatter_off_paths_steep_ground_water_and_structures() -> None:
    room = ops.sculpt_terrain_stroke(_room(), "raise", [[800, 600, 120]] * 3, 96)  # a steep mound
    room = ops.paint_terrain_stroke(room, "earth", [[128 + 16 * k, 200, 1.0] for k in range(40)], 40)  # a path
    room, pond = ops.place_blank(room, "r", "Pond", 300, 520)
    room = ops.set_water(room, pond, preset="natural_pond", width=160, height=128)
    room["settings"]["hd2d"]["structures"] = [{"id": "hut", "model": "assets/models/none.glb", "x": 700.0, "y": 300.0}]
    sweep = [[x, y] for x in range(64, 1000, 48) for y in range(64, 720, 48)]
    grass = ops.scatter_stroke(room, "Meadow", sweep, 64, seed=3)
    terrain = Terrain.from_ground(ops._parsed_ground(room))
    ground, _spots, _routes = ops.scatter_context(room)
    for name, (x, y, _t, _s) in _all(grass):
        assert terrain.material_at(x, y) == "grass", (name, x, y)
        assert terrain.surface_at(x, y)[1] >= math.cos(math.radians(35)) - 1e-6
        assert ground.water(x, y) is None or name.startswith("reeds")
        assert not ground.structure(x, y)
    assert not any(abs(x - 700) < 32 and abs(y - 300) < 32 for _n, (x, y, _t, _s) in _all(grass)), "the hut's spot"
    reeds = ops.scatter_stroke(room, "Pond edge", [[300, 520]], 96, seed=3)
    assert any(ground.water(x, y) is not None for _n, (x, y, _t, _s) in _all(reeds)), "reeds stand in the shallows"
    rocks = ops.scatter_stroke(room, "Rocks", [[x, 200] for x in range(140, 760, 48)], 48, seed=3)
    assert any(terrain.material_at(x, y) == "earth" for _n, (x, y, _t, _s) in _all(rocks)), "rocks may lie on paths"
    only_paths = ops.scatter_stroke(room, "Rocks", [[x, 200] for x in range(140, 760, 48)], 48, seed=3, on=["earth"])
    assert _all(only_paths) and all(terrain.material_at(x, y) == "earth" for _n, (x, y, _t, _s) in _all(only_paths))


def test_thinning_takes_a_share_once_and_removing_takes_all() -> None:
    room = ops.scatter_stroke(_room(), "Meadow", _line(), 96, seed=6)
    n = len(_all(room))
    thinned = ops.scatter_stroke(room, "all", _line(), 96, mode="thin", share=0.5, seed=1)
    assert 0.35 * n <= len(_all(thinned)) <= 0.65 * n, (n, len(_all(thinned)))
    gone = ops.scatter_stroke(room, "all", _line(), 128, mode="remove")
    assert "scatter" not in gone["settings"]["hd2d"]
    flowers_only = ops.scatter_stroke(room, "Wildflowers", _line(), 128, mode="remove")
    assert {a for a, _r in _all(flowers_only)} <= {"grass_tall"}
    assert ops.clear_scatter(room) == ops.clear_scatter(ops.clear_scatter(room))
    assert set(_rows(ops.clear_scatter(room, ["grass_tuft"]))) == set(_rows(room)) - {"grass_tuft"}


@pytest.mark.parametrize(("kwargs", "words"), [
    ({"collection": "Jungle"}, "Scatter one of"),
    ({"dabs": []}, "at least one"),
    ({"dabs": [[1, 2, 3]]}, r"must be \[x, y\]"),
    ({"density": 50}, "density"),
    ({"radius": 2}, "radius"),
    ({"mode": "grow"}, "adds, thins or removes"),
    ({"seed": 1.5}, "seed"),
    ({"on": ["lava"]}, "Scatter on"),
    ({"slope": 95}, "steepest slope"),
    ({"collection": {"grass_tuft": 1, "palm": 2}}, "Scatter one of"),
])
def test_bad_strokes_are_refused_with_the_reason(kwargs: dict[str, Any], words: str) -> None:
    args: dict[str, Any] = {"collection": "Meadow", "dabs": [[100, 100]], **kwargs}
    with pytest.raises(ops.OpError, match=words):
        ops.scatter_stroke(_room(), args.pop("collection"), args.pop("dabs"), **args)


@pytest.mark.parametrize(("raw", "words"), [
    ({"palm": [[1, 1, 0, 100]]}, "unknown asset"),
    ({"grass_tuft": [[1, 1, 0]]}, r"\[x, y, turn, size\]"),
    ({"grass_tuft": [[1.5, 1, 0, 100]]}, "whole numbers"),
    ({"grass_tuft": [[1, 1, 400, 100]]}, "out of range"),
    ({"grass_tuft": "x"}, "must be a list"),
    ({"grass_tuft": [[1, 1, 0, 100]] * (MAX_INSTANCES + 1)}, "at most"),
])
def test_broken_scatter_is_named_and_set_aside_alone(raw: Any, words: str) -> None:
    hd2d = {"ground": {"from": [0, 0], "to": [640, 480]}, "scatter": raw}
    with pytest.raises(Hd2dSettingsError, match=words):
        parse_hd2d(hd2d)
    lenient = parse_hd2d(hd2d, lenient=True)
    assert lenient.scatter == {} and lenient.scatter_error and lenient.ground is not None
    with pytest.raises(ops.OpError):
        ops.set_scatter(_room(), raw)


def test_only_what_blocks_blocks_and_it_stands_on_the_ground_as_it_is_now() -> None:
    from engine.hd2d.glb import load_glb

    models = {ASSETS["boulder"].model: load_glb(Path(ASSETS["boulder"].model))}
    room = ops.scatter_stroke(_room(), "Meadow", [[x, y] for x in range(64, 1000, 64) for y in range(64, 720, 64)],
                              64, seed=1)
    plain = World(parse_hd2d(_room()["settings"]["hd2d"]), models)
    grassy = World(parse_hd2d(room["settings"]["hd2d"]), models)
    assert grassy.walls == plain.walls and grassy._nav_grid() == plain._nav_grid(), "grass is walked through"
    room = ops.set_scatter(_room(), {"boulder": [[512, 384, 0, 100]]})
    world = World(parse_hd2d(room["settings"]["hd2d"]), models)
    assert [w.name for w in world.walls] == ["scatter:boulder"]
    assert world.stand(16.0, 12.0, 0.0, 0.25, 0.15) is None and world.stand(12.0, 12.0, 0.0, 0.25, 0.15) is not None
    raised = ops.sculpt_terrain_stroke(room, "raise", [[512, 384, 48]], 160)
    world.update_terrain(Terrain.from_ground(ops._parsed_ground(raised)))
    top = Terrain.from_ground(ops._parsed_ground(raised)).height(512, 384) / PX
    assert world.walls[0].lo[2] == pytest.approx(top, abs=0.05), "the boulder rose with the ground"
    assert _rows(raised) == _rows(room), "sculpting moves no instance"


def test_what_stands_in_the_way_and_what_breaks_its_own_rules_is_said() -> None:
    room = _room()
    room["entities"] = [{"id": "door", "name": "Cellar door", "x": 300, "y": 300, "behaviours": ["SceneTransition"]},
                        {"id": "npc", "name": "Elder", "x": 600, "y": 600,
                         "behaviour_config": {"Patrol": {"waypoints": [{"x": 600, "y": 600}, {"x": 900, "y": 600}]}}}]
    room = ops.set_scatter(room, {"boulder": [[310, 300, 0, 100], [750, 610, 0, 100], [100, 700, 0, 100]],
                                  "grass_tuft": [[300, 310, 0, 100]]})
    blocked, out_of_rule = ops.scatter_report(room)
    assert len(blocked) == 2 and "the door 'Cellar door'" in blocked[0] and "Elder's route" in blocked[1], blocked
    assert out_of_rule == {}
    painted = ops.paint_terrain_stroke(room, "stone", [[300, 310, 1.0]], 48)
    assert ops.scatter_report(painted)[1] == {"grass_tuft": 1}, "grass left standing on stone: said, not moved"


def test_ai_and_cli_scatter_with_studio_s_operations(tmp_path: Path) -> None:
    from engine import authoring_session
    from engine.project_scaffold import create_project
    from engine.studio_project import Project

    root = tmp_path / "game"
    create_project(root, "Game", template_id="hd2d_rpg")
    assert {"scatter_stroke", "set_scatter", "clear_scatter"} <= set(authoring.operations())
    for name in ("foliage.png", "rock_small.glb", "rock_medium.glb", "boulder.glb", "fallen_branch.glb"):
        assert (root / "assets" / "hd2d_starter" / "scatter" / name).is_file()
    project = Project(root, json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"])
    room = project.current
    before = json.loads(json.dumps(project.scene(room)))
    authoring.apply(project, [{"op": "scatter_stroke", "room": room, "collection": "Wildflowers",
                               "dabs": [[200, 200], [260, 220]], "radius": 64}])
    assert _rows(project.scene(room))
    lines = authoring._scatter_lines("Village", before, project.scene(room))
    assert lines and lines[0].startswith("Village: scatter +"), lines
    with pytest.raises(authoring.ChangeError, match="Scatter one of"):
        authoring.apply(project, [{"op": "scatter_stroke", "room": room, "collection": "Jungle", "dabs": [[1, 1]]}])
    project.save()
    result = authoring_session.apply(root, [{"op": "clear_scatter", "room": room}])
    assert result["ok"], result
    fresh = Project(root, json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"])
    assert "scatter" not in fresh.scene(room)["settings"]["hd2d"]


def test_the_brush_s_index_keeps_up_with_adds_and_removes() -> None:
    s = Scatter({"grass_tuft": [(10, 10, 0, 100)]})
    s.add("rock_small", (40, 40, 0, 100))
    assert {a for a, _r in s.near(30, 30, 20)} == {"rock_small"}
    s.remove("grass_tuft", (10, 10, 0, 100))
    assert s.count() == 1 and list(s.near(10, 10, 5)) == []
