"""Milestone 20A: sculpted ground, headless: its storage, heights, brushes, collision (walking up, cliffs blocking),
in-place rebuilds, the checked edits Studio and AI make, what sculpting leaves out of place, and water's ground shore.
The drawing is tests/test_terrain_gpu.py."""

from __future__ import annotations

import base64
import dataclasses
import json
import math
import random
from pathlib import Path
from typing import Any

import pytest

from engine import authoring, water
from engine import project_ops as ops
from engine.hd2d.settings import Hd2dSettingsError, parse_hd2d
from engine.hd2d.terrain import CHUNK, MAX_SLOPE, Terrain, TerrainError
from engine.hd2d.world import NAV_HALF, World

pytestmark = pytest.mark.fast
PX = 32.0


def _ground(size: tuple[float, float] = (640.0, 480.0), terrain: Any = None, elevation: float = 0.0) -> Any:
    raw: dict[str, Any] = {"from": [0, 0], "to": list(size), "elevation": elevation}
    if terrain is not None:
        raw["terrain"] = terrain
    return parse_hd2d({"ground": raw}).ground


def _room(terrain: Terrain | None = None) -> dict[str, Any]:
    ground: dict[str, Any] = {"from": [0, 0], "to": [640, 480]}
    if terrain is not None:
        ground["terrain"] = terrain.settings()
    return {"entities": [], "settings": {"world_width": 640, "world_height": 480, "hd2d": {"ground": ground}}}


def test_flat_ground_stores_nothing_and_the_same_heights_store_the_same_text() -> None:
    t = Terrain.from_ground(_ground())
    assert t.is_flat() and t.settings() == {}, "a flat ground is the plain ground"
    t.sculpt("raise", 320, 240, 96, 24)
    t.sculpt("lower", 100, 400, 64, 10)
    stored = t.settings()
    again = Terrain.from_ground(_ground(terrain=stored))
    assert again.heights == t.heights and json.dumps(again.settings()) == json.dumps(stored), "deterministic"
    assert list(stored["chunks"]) == sorted(stored["chunks"], key=lambda k: tuple(map(int, k.split(",")))[::-1])
    assert all(h == round(h / 0.25) * 0.25 for h in t.heights), "quarter-px steps"


@pytest.mark.parametrize(("terrain", "message"), [
    ({"cell": 12}, "cell must be one of"),
    ({"cells": 16}, "unknown keys"),
    ({"chunks": {"a,b": ""}}, "keys are 'i,j'"),
    ({"chunks": {"9,9": base64.b64encode(bytes(CHUNK * CHUNK * 2)).decode()}}, "outside the ground"),
    ({"chunks": {"0,0": "@@@"}}, "isn't base64"),
    ({"chunks": {"0,0": base64.b64encode(b"\x00\x01").decode()}}, "bytes"),
    ([], "must be an object"),
])
def test_bad_terrain_is_refused_with_the_reason(terrain: Any, message: str) -> None:
    with pytest.raises(Hd2dSettingsError, match=message):
        _ground(terrain=terrain)


def test_height_is_the_drawn_and_walked_triangles() -> None:
    t = Terrain.from_ground(_ground())
    rng = random.Random(3)
    for _ in range(20):
        t.sculpt(rng.choice(["raise", "lower"]), rng.uniform(0, 640), rng.uniform(0, 480), rng.uniform(16, 128),
                 rng.uniform(1, 30))
    cx_n, cy_n = t.chunk_count()
    tris = [tri for j in range(cy_n) for i in range(cx_n) for tri in t.chunk_triangles(i, j)]
    from engine.hd2d.world import _surface

    surfaces = [s for s in (_surface("g", True, tri) for tri in tris) if s is not None]
    for _ in range(300):
        x, y = rng.uniform(1, 639), rng.uniform(1, 479)
        on = [s.height(x / PX, y / PX) for s in surfaces]
        h = next(v for v in on if v is not None)
        assert t.height(x, y) / PX == pytest.approx(h, abs=1e-6)
    assert t.height(-5, 10) is None and t.height(10, 500) is None, "off the ground"


def test_brushes_raise_lower_smooth_and_flatten_with_a_soft_edge() -> None:
    t = Terrain.from_ground(_ground())
    t.sculpt("raise", 320, 240, 128, 32)
    assert t.height(320, 240) == pytest.approx(32, abs=0.5) and t.height(320 + 127, 240) < 1, "full at the centre"
    peak = t.height(320, 240)
    t.sculpt("smooth", 320, 240, 128, 1.0)
    assert t.height(320, 240) < peak, "smoothing takes the peak down"
    t.sculpt("flatten", 320, 240, 64, 1.0, target=8.0)
    assert t.height(320, 240) == pytest.approx(8.0, abs=0.25)
    t.sculpt("lower", 96, 96, 48, 20)  # (on a corner: between corners a height is read across them)
    assert t.height(96, 96) == pytest.approx(-20, abs=0.25)
    with pytest.raises(TerrainError, match="tool must be one of"):
        t.sculpt("dig", 0, 0, 10, 1)


def test_a_stroke_reports_the_chunks_it_changes_including_neighbours_on_its_edge() -> None:
    t = Terrain.from_ground(_ground((1024.0, 768.0)))
    edge = CHUNK * t.cell  # the corner column shared by chunks 0 and 1
    dirty = t.sculpt("raise", edge, 100, 12, 8)
    assert {(0, 0), (1, 0)} <= dirty
    assert t.sculpt("raise", 100, 100, 12, 8) == {(0, 0)}


def _world(t: Terrain) -> World:
    settings = parse_hd2d({"ground": {"from": [0, 0], "to": [640, 480], "terrain": t.settings()}})
    return World(settings, {})


def test_characters_walk_up_gentle_slopes_and_cliffs_stop_them() -> None:
    t = Terrain.from_ground(_ground())
    for _ in range(4):
        t.sculpt("raise", 320, 240, 192, 12)  # a 1.5 m hill, 6 m across: gentle
    for x in range(480, 640, 8):  # a 1.5 m wall in the east, its face less than a cell wide
        for y in range(0, 480, 8):
            t.sculpt("flatten", x, y, 10, 1.0, target=48.0)
    w = _world(t)
    x, z = 2.0, 0.0
    while x < 10.0:  # walking east over the hill, a frame's step at a time
        stood = w.stand(x + 0.06, 7.5, z, *NAV_HALF)
        assert stood is not None, (x, z)
        x, z = x + 0.06, stood[0]
    assert z == pytest.approx(t.height(x * PX, 7.5 * PX) / PX, abs=1e-6) and 1.4 < max(
        t.height(320, 240) / PX, 0) < 1.6
    x, z = 12.0, t.height(12 * PX, 7.5 * PX) / PX
    blocked = False
    while x < 16.0:
        stood = w.stand(x + 0.06, 7.5, z, *NAV_HALF)
        if stood is None:
            blocked = True
            break
        x, z = x + 0.06, stood[0]
    assert blocked and x < 15.0 and z < 0.5, "the wall's face is too steep to stand on"
    steep = [tri for j in range(2) for i in range(2) for tri in t.chunk_triangles(i, j)]
    from engine.hd2d.terrain import _face_normal

    assert any(_face_normal(*tri)[2] < MAX_SLOPE for tri in steep)


def test_rebuilding_only_the_changed_chunks_matches_a_fresh_world() -> None:
    t = Terrain.from_ground(_ground())
    w = _world(t)
    dirty = t.sculpt("raise", 300, 200, 80, 20)
    w.update_terrain(t, dirty)
    fresh = _world(t)
    rng = random.Random(5)
    for _ in range(200):
        x, y = rng.uniform(0.2, 19.8), rng.uniform(0.2, 14.8)
        assert sorted(round(h, 6) for h, _s in w.heights_at(x, y)) == sorted(round(h, 6) for h, _s in fresh.heights_at(x, y))
    assert len(w.surfaces) == len(fresh.surfaces)


def test_a_ray_meets_the_sculpted_ground_where_it_is() -> None:
    t = Terrain.from_ground(_ground())
    t.sculpt("raise", 320, 240, 160, 48)
    hit = t.ray((10.0, -20.0, 30.0), (0.0, 0.6, -0.8))
    assert hit is not None and hit[2] == pytest.approx(t.height(hit[0] * PX, hit[1] * PX) / PX, abs=0.002)
    assert t.ray((10.0, 7.0, 30.0), (0.0, 0.0, 1.0)) is None, "looking up"


def test_sculpting_is_one_checked_edit_and_flat_again_is_the_plain_ground() -> None:
    room = _room()
    raised = ops.sculpt_terrain(room, "raise", 320, 240, 96, 16)
    ground = raised["settings"]["hd2d"]["ground"]
    assert ground["terrain"]["cell"] == 16 and ground["terrain"]["chunks"]
    assert "terrain" not in room["settings"]["hd2d"]["ground"], "the room given is untouched"
    back = ops.sculpt_terrain(raised, "lower", 320, 240, 96, 16)
    assert "terrain" not in back["settings"]["hd2d"]["ground"], "flat again: no terrain key"
    assert "terrain" not in ops.flatten_all_terrain(raised)["settings"]["hd2d"]["ground"]


@pytest.mark.parametrize(("kwargs", "message"), [
    ({"tool": "dig"}, "tool is one of"),
    ({"radius": 4}, "radius must be between"),
    ({"strength": 900}, "strength must be between"),
    ({"tool": "smooth", "strength": 2}, "share of the way"),
    ({"x": 5000}, "off the room's ground"),
])
def test_bad_strokes_are_refused_with_the_reason(kwargs: dict[str, Any], message: str) -> None:
    args = {"tool": "raise", "x": 320, "y": 240, "radius": 64, "strength": 8, **kwargs}
    with pytest.raises(ops.OpError, match=message):
        ops.sculpt_terrain(_room(), **args)


def test_a_room_that_isn_t_hd2d_has_no_ground_to_sculpt() -> None:
    with pytest.raises(ops.OpError, match="isn't an HD-2D room"):
        ops.sculpt_terrain({"entities": [], "settings": {}}, "raise", 0, 0)


def test_sculpting_never_moves_what_stands_there_and_says_what_it_left_out_of_place() -> None:
    room = _room()
    room["settings"]["hd2d"]["structures"] = []
    room["entities"] = [{"id": "e", "name": "Elder", "x": 320.0, "y": 240.0, "elevation": 0.0}]
    assert ops.terrain_anchoring(room) == []
    raised = ops.sculpt_terrain(room, "raise", 320, 240, 96, 32)
    assert raised["entities"] == room["entities"], "not moved"
    said = ops.terrain_anchoring(raised, room)  # (judged under his feet, half a metre below his picture's centre)
    assert len(said) == 1 and said[0].startswith("'Elder' is 0.") and said[0].endswith("m below the ground"), said
    assert ops.anchoring_ids(raised, room) == ["e"]
    settled = ops.settle_on_ground(raised, ["e"])
    assert ops.terrain_anchoring(settled) == [] and settled["entities"][0]["elevation"] > 16, "stood back on it"
    # someone on a platform (never on the ground) isn't this edit's doing: only what the edit moved off it is said
    up = {**room, "entities": [{"id": "p", "name": "Guard", "x": 100.0, "y": 100.0, "elevation": 64.0}]}
    assert ops.terrain_anchoring(up) == ["'Guard' is 2.0 m above the ground"]
    assert ops.terrain_anchoring(ops.sculpt_terrain(up, "raise", 320, 240, 96, 32), up) == []
    with pytest.raises(ops.OpError, match="Name the objects"):
        ops.settle_on_ground(raised, [])


def test_ai_sculpts_with_the_same_operation(tmp_path: Path) -> None:
    from engine.project_scaffold import create_project
    from engine.studio_project import Project

    root = tmp_path / "game"
    create_project(root, "Game", template_id="hd2d_rpg")
    project = Project(root, json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"])
    room = project.current
    authoring.apply(project, [{"op": "sculpt_terrain", "room": room, "tool": "raise", "x": 320, "y": 320,
                               "radius": 96, "strength": 16}])
    assert project.scene(room)["settings"]["hd2d"]["ground"]["terrain"]["chunks"]
    with pytest.raises(authoring.ChangeError, match="tool is one of"):
        authoring.apply(project, [{"op": "sculpt_terrain", "room": room, "tool": "dig", "x": 1, "y": 1}])
    assert {"sculpt_terrain", "sculpt_terrain_stroke", "flatten_all_terrain", "settle_on_ground"} <= set(
        authoring.operations()), "Studio's stroke and the settle answer are the AI's and the CLI's too"
    authoring.apply(project, [{"op": "sculpt_terrain_stroke", "room": room, "tool": "lower", "radius": 64,
                               "dabs": [[300, 300, 4], [320, 304, 4]]}])


def test_water_can_take_the_ground_as_its_shore() -> None:
    assert water.parse_water({"preset": "natural_pond", "shore": "terrain"}).shore == "terrain"
    with pytest.raises(water.WaterError, match="simple pond has no shore"):
        water.parse_water({"preset": "pond", "shore": "terrain"})


def test_flat_rooms_read_as_before() -> None:
    g = _ground()
    assert g.terrain is None and dataclasses.asdict(g) == {"texture": None, "lo": (0.0, 0.0), "hi": (640.0, 480.0),
                                                           "elevation": 0.0, "terrain": None}
    plain = parse_hd2d({"ground": {"from": [0, 0], "to": [64, 64], "extra": 1}}).ground
    assert plain is not None, "unknown ground keys are still ignored, as before"
    assert math.isclose(World(parse_hd2d({"ground": {"from": [0, 0], "to": [64, 64]}}), {}).surfaces[0].plane[2], 0.0)


def test_settling_the_shared_player_settles_it_in_its_room_only(tmp_path: Path) -> None:
    """QA: the player is shared across rooms; where it starts (x, y and now its elevation) is each room's own."""
    from engine.project_scaffold import create_project
    from engine.studio_project import Project

    root = tmp_path / "game"
    create_project(root, "Game", template_id="hd2d_rpg")
    project = Project(root, json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"])
    rooms = [key for key, _label, _path in project.rooms()]
    room, other = rooms[0], next(r for r in rooms if r != rooms[0])
    pid = next(e["id"] for e in project.scene(room)["entities"] if project.is_shared_player(e.get("id"), room))
    oid = next(e["id"] for e in project.scene(other)["entities"] if project.is_shared_player(e.get("id"), other))
    before = project.scene(other)
    player = ops.find_entity(project.scene(room), pid)
    authoring.apply(project, [{"op": "sculpt_terrain", "room": room, "tool": "raise", "x": player["x"],
                               "y": player["y"], "radius": 96, "strength": 24},
                              {"op": "settle_on_ground", "room": room, "entity_ids": [pid]}])
    assert ops.find_entity(project.scene(room), pid).get("elevation", 0) > 8, "settled up onto the raised ground"
    was = ops.find_entity(before, oid).get("elevation")
    assert ops.find_entity(project.scene(other), oid).get("elevation") == was, "the other room's player starts as it did"
    assert ops.ROOM_PLAYER_FIELDS == ("id", "x", "y", "elevation")


# --- Milestone 20B: live strokes' contract, partial saving, anchoring and the shared player -------------------------

def test_a_whole_stroke_is_one_checked_edit_that_replays_exactly() -> None:
    """Studio records a stroke's dabs and commits them through sculpt_terrain_stroke: applying the same dabs to the
    same ground gives the same heights (what was shown is what is saved), and only the chunks it changed are stored
    afresh."""
    room = ops.sculpt_terrain(_room(), "raise", 100, 100, 64, 12)  # some ground stored already
    dabs = [[200 + 6 * k, 240 + 2 * k, 3.5] for k in range(40)]
    live, exact = Terrain.from_ground(ops._parsed_ground(room)), {}
    for x, y, s in dabs:
        live.sculpt("raise", x, y, 48, s, exact=exact)
    saved = ops.sculpt_terrain_stroke(room, "raise", dabs, 48)
    assert Terrain.from_ground(ops._parsed_ground(saved)).heights == live.heights
    full = Terrain.from_ground(ops._parsed_ground(saved))
    assert saved["settings"]["hd2d"]["ground"]["terrain"]["chunks"] == full.chunks(), "partial encoding = full"


@pytest.mark.parametrize("tool", ["raise", "flatten", "smooth"])
def test_many_small_dabs_add_up_as_few_big_ones_do(tool: str) -> None:
    """QA: a held brush dabs once a frame; below the stored step (0.25 px) each dab once rounded away, so what a
    stroke did depended on the frame rate. Exact heights are carried through the stroke instead."""
    room = ops.sculpt_terrain(_room(), "raise", 320, 240, 160, 48)
    rate = {"raise": 3.2, "flatten": 0.3, "smooth": 1.0}[tool]  # 0.1 m a second; shares of the way a second

    def held(fps: int) -> list[float]:
        dt = 1 / fps
        amount = rate * dt if tool == "raise" else 1 - math.exp(-rate * dt)
        out = ops.sculpt_terrain_stroke(room, tool, [[300, 220, round(amount, 6)]] * (2 * fps), 96, 0.0)
        return Terrain.from_ground(ops._parsed_ground(out)).heights

    start = Terrain.from_ground(ops._parsed_ground(room)).heights
    slow, fast = held(30), held(240)
    moved = max(abs(a - b) for a, b in zip(slow, start))
    assert moved > (1 if tool == "smooth" else 4), "two seconds of a slow brush do something"
    assert max(abs(a - b) for a, b in zip(slow, fast)) <= 0.5, "and the same at 30 and 240 frames a second"


@pytest.mark.parametrize(("dabs", "message"), [
    ([], "at least one"),
    ([[1, 2]], r"must be \[x, y, strength\]"),
    ([[1, 2, "a"]], "strength must be a number"),
    ([[5000, 5000, 1]], "off the room's ground"),
    ("x", "list of"),
])
def test_bad_strokes_are_refused_whole(dabs: Any, message: str) -> None:
    with pytest.raises(ops.OpError, match=message):
        ops.sculpt_terrain_stroke(_room(), "raise", dabs, 48)
    with pytest.raises(ops.OpError, match="share of the way"):
        ops.sculpt_terrain_stroke(_room(), "smooth", [[10, 10, 3]], 48)
    with pytest.raises(ops.OpError, match="at most"):
        ops.sculpt_terrain_stroke(_room(), "raise", [[10, 10, 1]] * (ops.STROKE_DABS + 1), 48)


def test_a_flatten_stroke_without_a_target_flattens_to_its_start() -> None:
    room = ops.sculpt_terrain(_room(), "raise", 320, 240, 160, 32)
    start = Terrain.from_ground(ops._parsed_ground(room)).height(320, 240)
    out = ops.sculpt_terrain_stroke(room, "flatten", [[320, 240, 1.0], [360, 240, 1.0], [400, 240, 1.0]], 32)
    t = Terrain.from_ground(ops._parsed_ground(out))
    assert t.height(400, 240) == pytest.approx(start, abs=0.5)


def test_grass_beside_dirt_gets_the_fringe_and_a_gentle_basin_none() -> None:
    t = Terrain.from_ground(_ground())
    t.sculpt("lower", 320, 240, 160, 24)  # a gentle basin: no dirt, so no fringe
    assert all(not t.chunk_mesh(ci, cj)[1] and not t.chunk_mesh(ci, cj)[2] for ci in range(3) for cj in range(2))
    for _ in range(3):
        t.sculpt("raise", 320, 240, 96, 24)  # a mound with steep faces: dirt, and grass beside it fringed
    gentle, fringe, steep = t.chunk_mesh(1, 1)
    assert gentle and fringe and steep


def test_anchoring_reports_water_left_dry_or_in_the_air_and_settles_structures() -> None:
    room = _room()
    room["settings"]["hd2d"]["structures"] = [{"id": "hut", "model": "assets/m.glb", "x": 320.0, "y": 240.0,
                                               "elevation": 0.0}]
    scene, pid = ops.place_blank(room, "r", "Pond", 160.0, 120.0)
    scene = ops.set_water(scene, pid, preset="natural_pond", width=96, height=64, shore="grass")
    raised = ops.sculpt_terrain(scene, "raise", 160, 120, 160, 32)  # the ground rises over the pond's level
    words = ops.terrain_anchoring(raised, scene)
    assert any("'Pond' (water) is under the ground" in w for w in words), words
    raised = ops.sculpt_terrain(raised, "raise", 320, 240, 96, 24)
    assert "hut" in ops.anchoring_structure_ids(raised, scene)
    settled = ops.settle_on_ground(raised, [], ["hut"])
    assert ops.find_structure(settled, "hut")["elevation"] > 16
    lowered = ops.sculpt_terrain(scene, "lower", 160, 120, 160, 32)
    assert any("(water) stands" in w for w in ops.terrain_anchoring(lowered, scene)), "a banked pond in the air"


def test_a_hand_made_shared_player_keeps_its_elevation_without_migration() -> None:
    """A shared player definition carrying an elevation stays as it is when a room is saved (no silent migration);
    a room keeps its own elevation only where it differs."""
    shared = {"tag": "player", "sprite": "p.png", "elevation": 18.0}
    room = {"entities": [{"id": "p1", "prefab_id": "player", "x": 1.0, "y": 2.0}]}
    expanded = ops.expand_players(room, shared)
    stored, definition = ops.split_players(expanded, ["p1"], shared)
    assert definition is not None and definition.get("elevation") == 18.0, "the definition keeps it"
    assert "elevation" not in ops.find_entity(stored, "p1"), "the room doesn't copy it"
    moved = {**expanded, "entities": [{**expanded["entities"][0], "elevation": 40.0}]}
    stored2, definition2 = ops.split_players(moved, ["p1"], shared)
    assert ops.find_entity(stored2, "p1")["elevation"] == 40.0 and definition2["elevation"] == 18.0


def test_a_valley_dug_under_a_structure_is_reported_but_a_bridge_already_above_the_ground_is_not() -> None:
    room = _room()
    room["settings"]["hd2d"]["structures"] = [
        {"id": "hut", "model": "assets/m.glb", "x": 160.0, "y": 240.0, "elevation": 0.0},
        {"id": "bridge", "model": "assets/m.glb", "x": 480.0, "y": 240.0, "elevation": 64.0}]
    assert ops.anchoring_structure_ids(room) == ["bridge"], "a bridge stands above the ground by design"
    dug = ops.sculpt_terrain(ops.sculpt_terrain(room, "lower", 160, 240, 128, 48), "lower", 480, 240, 128, 48)
    assert ops.anchoring_structure_ids(dug, room) == ["hut"], "only what the edit left out of place"
    assert any(w.startswith("'hut' is") and w.endswith("above the ground") for w in ops.terrain_anchoring(dug, room))
    assert ops.find_structure(dug, "hut")["elevation"] == 0.0, "reported, never moved"


def test_the_cli_sculpts_a_room_that_isn_t_the_first(tmp_path: Path) -> None:
    """QA: with Studio closed, a change to a room not yet loaded crashed (the dry run's copy of the project lacked
    when each file was read)."""
    from engine import authoring_session
    from engine.project_scaffold import create_project
    from engine.studio_project import Project

    root = tmp_path / "game"
    create_project(root, "Game", template_id="hd2d_rpg")
    world_file = root / json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"]
    world = json.loads(world_file.read_text(encoding="utf-8"))
    world["start_scene"] = "cottage"  # (so the room with ground, "start", is one the project hasn't loaded)
    world_file.write_text(json.dumps(world), encoding="utf-8")
    other = "start"
    result = authoring_session.apply(root, [{"op": "sculpt_terrain_stroke", "room": other, "tool": "raise",
                                             "radius": 64, "dabs": [[200, 200, 8]]}])
    assert result["ok"], result
    fresh = Project(root, json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"])
    assert fresh.scene(other)["settings"]["hd2d"]["ground"]["terrain"]["chunks"]
