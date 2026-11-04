"""#461 R4B: where characters may go into water, headless.

- ``passable`` on rivers and ponds: "auto" (as before: a river waded up to half a metre, a pond by ``walkable``),
  "wade" (up to ``wade_depth``), "block" (not entered), whatever the water looks like or how deep its bed is carved;
  stored only when set, checked, older scenes as they were.
- Ponds that block or are waded to a depth do so by their outline, where their water is drawn (with the sculpted
  ground as their shore: where water stands over it), not by the box round them; a bridge's deck over water stays dry.
- ``World.ways_out``: the nearest places a character put in water it can't stand in could walk out to, the same
  every time. The real window (Play, Studio, NPCs walking out, export) is tests/test_water_passable_gpu.py."""

from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import Any

import pytest

from engine import project_ops as ops
from engine import water
from engine.hd2d import river
from engine.hd2d.settings import parse_hd2d
from engine.hd2d.world import DEEP, World, _surface

pytestmark = pytest.mark.fast

P = 32.0
STREAM = [[4.0, 600.0, 96.0, -16.0], [800.0, 610.0, 96.0, -16.0], [1596.0, 600.0, 96.0, -16.0]]  # edge to edge
POND = (1200.0, 300.0, 320.0, 192.0)  # px: x, y, width, height (an ellipse: x 1040..1360, y 204..396)


def _room(*, river_args: dict[str, Any] | None = None, pond: dict[str, Any] | None = None,
          depths: list[float] | None = None) -> dict[str, Any]:
    scene = {"entities": [], "settings": {"world_width": 1600, "world_height": 1200,
                                          "hd2d": {"ground": {"texture": "assets/textures/grass.png",
                                                              "from": [0, 0], "to": [1600, 1200]}}}}
    scene = ops.add_river(scene, "stream", STREAM, **(river_args or {}))
    scene = ops.carve_river_bed(scene, "stream", depths=depths or [0.8, 0.3, 0.8])  # (deep; a ford mid-way)
    if pond is not None:
        scene, pid = ops.place_blank(scene, "start", "Lake", POND[0], POND[1])
        scene = ops.set_water(scene, pid, preset="natural_pond", shape="ellipse", width=POND[2], height=POND[3],
                              **pond)
    return scene


def _world(scene: dict[str, Any]) -> World:
    return World(parse_hd2d(scene["settings"]["hd2d"]), {}, river.ponds_of(scene["entities"]))


def _floor(world: World, x_px: float, y_px: float) -> float:
    return min(h for h, _s in world.heights_at(x_px / P, y_px / P))


def _stands(world: World, x_px: float, y_px: float, z: float | None = None) -> bool:
    z = _floor(world, x_px, y_px) if z is None else z
    return world.stand(x_px / P, y_px / P, z, 0.3, 0.19) is not None


def test_passable_is_stored_only_when_set_checked_and_older_rivers_and_ponds_are_as_they_were() -> None:
    plain = _room(pond={})
    assert ops.rivers(plain)[0].keys() == {"id", "points"}, "a river as before: no new keys"
    entity = ops.entities(plain)[0]
    assert "passable" not in entity["behaviour_config"]["WaterSurface"], "a pond as before"
    waded = ops.set_river(plain, "stream", passable="wade", wade_depth=1.2)
    assert ops.rivers(waded)[0]["passable"] == "wade" and ops.rivers(waded)[0]["wade_depth"] == 1.2
    assert ops.rivers(ops.set_river(waded, "stream", passable="auto", wade_depth=1.0))[0].keys() == {"id", "points"}
    with pytest.raises(ops.OpError, match="passable must be one of auto, wade, block"):
        ops.set_river(plain, "stream", passable="swim")
    with pytest.raises(ops.OpError, match="wade_depth"):
        ops.set_river(plain, "stream", passable="wade", wade_depth=3.0)
    blocked = ops.set_water(plain, entity["id"], passable="block")
    assert ops.water_of(ops.find_entity(blocked, entity["id"]))["passable"] == "block"
    assert ops.find_entity(blocked, entity["id"])["solid"] is True, "a 2D room still blocks by its box (a solid)"
    with pytest.raises(ops.OpError, match="passable must be one of"):
        ops.set_water(plain, entity["id"], passable="swim")
    assert water.blocks(water.parse_water({"preset": "pond", "walkable": False})), "auto: by walkable, as before"
    assert not water.blocks(water.parse_water({"preset": "pond", "passable": "wade", "walkable": False}))


def test_a_river_s_water_is_walked_by_its_passable_not_its_look_or_carved_depth() -> None:
    deep_x, ford_x = 200.0, 800.0  # (its bed 0.8 m deep there; a 0.3 m ford mid-way)
    auto = _world(_room())
    assert not _stands(auto, deep_x, 600) and _stands(auto, ford_x, 610), "auto: as R3 (deep stops, a ford waded)"
    wade = _world(_room(river_args={"passable": "wade", "wade_depth": 1.0}))
    assert _stands(wade, deep_x, 600), "wade 1 m: the 0.8 m water waded"
    shallow = _world(_room(river_args={"passable": "wade", "wade_depth": 0.2}))
    assert not _stands(shallow, ford_x, 610), "wade 0.2 m: even the ford's 0.3 m is too deep"
    block = _world(_room(river_args={"passable": "block"}))
    assert not _stands(block, ford_x, 610) and not _stands(block, ford_x, 650), "block: not even the ford's edge"
    assert _stands(block, ford_x, 720), "the bank beside it: dry"
    assert block.water_at(ford_x / P, 610 / P, _floor(block, ford_x, 610)) is not None, "(it is water, waded or not)"
    # a bridge's deck over the blocked water (a floor surface 2 m up): dry, walked
    x0, x1, y0, y1 = 760.0 / P, 840.0 / P, 500.0 / P, 720.0 / P
    for tri in (((x0, y0, 2.0), (x1, y0, 2.0), (x1, y1, 2.0)), ((x0, y0, 2.0), (x1, y1, 2.0), (x0, y1, 2.0))):
        deck = _surface("bridge/deck", False, tri)
        assert deck is not None
        block.surfaces.append(deck)
        block._add_to_index(deck)
    assert _stands(block, ford_x, 610, 2.0), "on the deck: dry"
    assert block.path((ford_x / P, 515 / P, 2.0), (ford_x / P, 705 / P, 2.0)), "across on the deck"
    assert block.path((ford_x / P, 720 / P, 0.0), (ford_x / P, 480 / P, 0.0)) == [] or all(
        z >= 1.9 for _x, _y, z in block.path((ford_x / P, 720 / P, 0.0), (ford_x / P, 480 / P, 0.0))[1:-1]
        if 560 / P < _y < 660 / P), "never through the water itself"


def test_a_blocking_pond_blocks_where_its_water_is_not_the_box_round_it() -> None:
    scene = _room(pond={"walkable": False})  # (auto, walk through it off: blocks, as before)
    world = _world(scene)
    assert not _stands(world, 1200, 300), "in its water"
    assert _stands(world, 1060, 220), "in its box's corner, outside its water: no invisible wall"
    walkable = _world(_room(pond={}))
    assert _stands(walkable, 1200, 300), "a walkable pond: walked, as before"
    gated = copy.deepcopy(scene)
    ops.entities(gated)[0]["require_flags"] = ["rain"]
    assert _stands(_world(gated), 1200, 300), "shown only when flags say: its box, which its flags hide (as before)"
    # its shore the sculpted ground: blocked where its water stands over the ground, not on dry ground inside it
    shore = _room(pond={"walkable": False, "shore": "terrain"})
    pid = ops.entities(shore)[0]["id"]
    ops.find_entity(shore, pid)["elevation"] = -8.0  # (its water 0.25 m down; the ground lowered under its middle)
    shore = ops.sculpt_terrain_stroke(shore, "flatten", [[1200, 300, 1.0]], radius=72, target=-24.0)
    shore = ops.sculpt_terrain_stroke(shore, "flatten", [[1320, 300, 1.0]] * 6, radius=40, target=-7.0)  # 3 cm over
    world = _world(shore)
    assert not _stands(world, 1200, 300), "where its water stands over the ground"
    assert _stands(world, 1320, 300), "inside its outline, the ground just above its water: dry, walked"


def test_wading_a_pond_to_a_depth_and_the_river_mouth_into_a_blocking_pond() -> None:
    basin = _room(pond={"passable": "wade", "wade_depth": 0.4, "shore": "terrain"})
    basin = ops.sculpt_terrain_stroke(basin, "flatten", [[1200, 300, 1.0]], radius=72, target=-24.0)  # 0.75 m
    basin = ops.sculpt_terrain_stroke(basin, "flatten", [[1300, 300, 1.0]], radius=20, target=-8.0)  # 0.25 m
    world = _world(basin)
    assert not _stands(world, 1200, 300) and _stands(world, 1300, 300), "0.75 m: too deep; 0.25 m: waded"
    # a river flowing into a blocking pond: its own rule up to the shore, the pond's from its outline on
    into = [[400.0, 240.0, 48.0, 0.0], [800.0, 250.0, 48.0, 0.0], [1180.0, 240.0, 48.0, 0.0]]  # (off its middle)
    scene = {"entities": [], "settings": {"world_width": 1600, "world_height": 1200,
                                          "hd2d": {"ground": {"texture": "assets/textures/grass.png",
                                                              "from": [0, 0], "to": [1600, 1200]}}}}
    scene, pid = ops.place_blank(scene, "start", "Lake", POND[0], POND[1])
    scene = ops.set_water(scene, pid, preset="natural_pond", shape="ellipse", width=POND[2], height=POND[3],
                          walkable=False)
    scene = ops.carve_river_bed(ops.add_river(scene, "stream", into, mouth="auto"), "stream", depths=[0.3] * 3)
    world = _world(scene)
    mouth = river.join(river.parse_rivers(scene["settings"]["hd2d"]["rivers"])[0], river.ponds_of(scene["entities"]))
    shore = mouth.at[0] * P
    assert _stands(world, shore - 24, 240), "the river's shallows just short of the shore: waded"
    assert not _stands(world, shore + 24, 240), "past the shore: the lake, blocking"
    box_left = POND[0] - POND[2] / 2
    assert box_left < shore - 24, "(where the old box would have stopped it: before the shore)"


def test_ways_out_are_the_nearest_standing_places_the_same_every_time() -> None:
    world = _world(_room())
    x, y = 200.0 / P, 600.0 / P  # in the deep stretch
    bed = _floor(world, 200, 600)
    assert world.stand(x, y, bed, 0.3, 0.19) is None
    ways = world.ways_out(x, y, bed)
    assert ways == _world(_room()).ways_out(x, y, bed), "deterministic"
    assert 1 <= len(ways) <= 4 and all(world.stand(wx, wy, wz, 0.3, 0.19) is not None for wx, wy, wz in ways)
    dists = [((wx - x) ** 2 + (wy - y) ** 2) ** 0.5 for wx, wy, _wz in ways]
    assert dists == sorted(dists) and dists[0] < 3.0, dists
    assert world.ways_out(x, y, bed, radius=0.4) == [], "none near enough: none"


def test_auto_keeps_r3_s_depth_rule_exactly() -> None:
    world = _world(_room())
    for x in range(40, 1560, 37):
        for y in range(540, 680, 9):
            floor = _floor(world, x, y)
            depth = world.deepest(x / P, y / P, floor, 0.3, 0.19)
            assert (world.stand(x / P, y / P, floor, 0.3, 0.19) is None) == (depth > DEEP + 0.01), (x, y, depth)


class _Walker(SimpleNamespace):
    """A sprite-like character: 32 x 48 px, its feet box the bottom quarter (as the player's)."""

    @property
    def bottom(self) -> float:
        return float(self.center_y) - float(self.height) / 2


def _npc(world: World, x_px: float, y_px: float, route: list[list[float]]) -> tuple[Any, Any]:
    from engine.behaviours.floor_route import FloorRouteBehaviour

    z = _floor(world, x_px, y_px)
    npc = _Walker(center_x=x_px, center_y=y_px + 18, width=32.0, height=48.0, scale_x=1.0, mesh_name="Npc",
                  mesh_entity_data={"elevation": z * P, "components": {"collider": {"kind": "box", "auto": True}}})
    window = SimpleNamespace(hd2d_world=world, scene_controller=None)
    return npc, FloorRouteBehaviour(npc, window, route=route, speed=60.0, wait=0.0)


def test_an_npc_put_in_deep_water_walks_out_never_deeper_and_then_keeps_its_route() -> None:
    from engine.physics_runtime import _sprite_to_aabb

    world = _world(_room())
    npc, route = _npc(world, 200.0, 600.0, [[200.0, 800.0, 0.0], [300.0, 800.0, 0.0]])  # (in the deep stretch)
    box = _sprite_to_aabb(npc)
    start = world.deepest(box.x / P, box.y / P, npc.mesh_entity_data["elevation"] / P, 0.3, 0.19)
    assert start > DEEP, "it starts in deep water"
    last, deepest, moves = (npc.center_x, npc.center_y), start, []
    for _ in range(900):
        route.update(1 / 60)
        box = _sprite_to_aabb(npc)
        z = npc.mesh_entity_data["elevation"] / P
        deepest = max(deepest, world.deepest(box.x / P, box.y / P, z, 0.3, 0.19))
        moves.append(((npc.center_x - last[0]) ** 2 + (npc.center_y - last[1]) ** 2) ** 0.5)
        last = (npc.center_x, npc.center_y)
    assert deepest <= start + 0.05 + 1e-9, ("never deeper than where it was put", start, deepest)
    assert max(moves) <= 60.0 / 60 + 1e-6, "walked, never moved further than a step a frame (no teleport)"
    assert world.stand(box.x / P, box.y / P, z, 0.3, 0.19) is not None, "out: it can stand"
    assert getattr(npc, "mesh_hd2d_stranded", None) is None and npc.center_y > 700, "and it walks on its route"


def test_an_npc_with_no_way_out_is_stranded_said_once_and_doesn_t_loop(caplog: pytest.LogCaptureFixture,
                                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    scene = _room()
    scene, pid = ops.place_blank(scene, "start", "Big lake", 800.0, 300.0)
    scene = ops.set_water(scene, pid, preset="natural_pond", shape="ellipse", width=900.0, height=560.0,
                          passable="block")  # (8.75 m to its shore from its middle: further than a way out is looked for)
    world = _world(scene)
    npc, route = _npc(world, 800.0, 300.0, [[200.0, 800.0, 0.0]])
    calls = {"ways": 0}
    real = world.ways_out

    def counted(*args: Any, **kwargs: Any) -> Any:
        calls["ways"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(world, "ways_out", counted)
    with caplog.at_level("WARNING"):
        for _ in range(600):
            route.update(1 / 60)
    assert npc.mesh_hd2d_stranded and "can't walk out of the water" in npc.mesh_hd2d_stranded
    assert sum("is stranded" in r.message for r in caplog.records) == 1, "said once"
    assert calls["ways"] == 2, "looked for a way out at first and again after RETRY_S (10 s here), not every frame"
    assert (npc.center_x, npc.center_y) == (800.0, 318.0), "stayed where it was"


# --- independent review of 6c0288b -----------------------------------------------------------------------------


def _flat_room(**pond: Any) -> dict[str, Any]:
    scene = {"entities": [], "settings": {"world_width": 1600, "world_height": 1200,
                                          "hd2d": {"ground": {"texture": "assets/textures/grass.png",
                                                              "from": [0, 0], "to": [1600, 1200]}}}}
    scene, pid = ops.place_blank(scene, "start", "Lake", 800.0, 600.0)
    return ops.set_water(scene, pid, preset="natural_pond", shape="ellipse", width=640.0, height=400.0, **pond)


def test_one_put_in_blocking_water_can_only_walk_out_never_across() -> None:
    """Pond water drawn over flat ground is as deep everywhere: one put just inside walked straight across it."""
    for pond in ({"passable": "block"}, {"walkable": False}):
        world = _world(_flat_room(**pond))
        walker = _Walker(center_x=500.0, center_y=600.0 + 18, width=32.0, height=48.0, scale_x=1.0,
                         mesh_entity_data={"elevation": 0.0, "components": {"collider": {"kind": "box", "auto": True}}})
        for _ in range(400):
            world.move(walker, (2.0, 0.0), [])
        assert walker.center_x < 520.0, ("not on across it", pond, walker.center_x)
        for _ in range(100):
            world.move(walker, (-2.0, 0.0), [])
        assert walker.center_x < 470.0, ("out, the near way", pond, walker.center_x)
    # a blocked river standing over flat ground (uncarved: as deep everywhere): out to a bank, never across
    scene = {"entities": [], "settings": {"world_width": 1600, "world_height": 1200,
                                          "hd2d": {"ground": {"texture": "assets/textures/grass.png",
                                                              "from": [0, 0], "to": [1600, 1200]}}}}
    scene = ops.add_river(scene, "stream", [[4.0, 600.0, 192.0, 8.0], [1596.0, 600.0, 192.0, 8.0]], passable="block")
    world = _world(scene)
    walker = _Walker(center_x=800.0, center_y=520.0 + 18, width=32.0, height=48.0, scale_x=1.0,
                     mesh_entity_data={"elevation": 0.0, "components": {"collider": {"kind": "box", "auto": True}}})
    for _ in range(300):
        world.move(walker, (0.0, 2.0), [])
    assert walker.center_y - 18 < 560.0, ("not on across it", walker.center_y)


def test_a_pond_on_a_raised_floor_doesn_t_block_the_ground_under_it() -> None:
    scene = _flat_room(passable="block")
    ops.entities(scene)[0]["elevation"] = 64.0  # (a roof pool, 2 m up)
    world = _world(scene)
    assert world.stand(800 / P, 600 / P, 0.0, 0.3, 0.19) is not None, "the ground under it: walked"


def test_a_wide_npc_judged_by_its_own_feet_plans_a_bounded_number_of_times_and_says_so_once(
        monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """Review of 6c0288b: judged by the navigation grid's footprint, an NPC with a wide feet box froze in the water
    and planned again and again, never saying so."""
    world = _world(_room())
    npc, route = _npc(world, 200.0, 600.0, [[200.0, 800.0, 0.0], [300.0, 800.0, 0.0]])
    npc.width = 128.0  # (a 4 m picture: its own feet box 2.4 m wide fits nowhere in the 3 m channel)
    planned = {"n": 0}
    real = world.path

    def counted(*args: Any) -> Any:
        planned["n"] += 1
        return real(*args)

    monkeypatch.setattr(world, "path", counted)
    with caplog.at_level("WARNING"):
        for _ in range(60 * 30):
            route.update(1 / 60)
    said = [r.message for r in caplog.records if "is stranded" in r.message or "can't get through" in r.message]
    assert len(said) == 1, ("said once, not frozen silently", said)
    # (REPLANS tries, then BACK_OFF_S: about 3 every 7 s; before the review, 34 in 30 s and never said)
    assert planned["n"] <= 16, ("planned a bounded number of times in 30 s", planned["n"])


def test_blocking_set_and_cleared_through_every_path() -> None:
    scene = _flat_room()
    pid = ops.entities(scene)[0]["id"]
    blocked = ops.set_water(scene, pid, passable="block")
    gone = ops.find_entity(ops.remove_water(blocked, pid), pid)
    assert "solid" not in gone and "components" not in gone, "removed water leaves no wall"
    hand = copy.deepcopy(ops.set_water(scene, pid, passable="wade", walkable=False))
    ops.find_entity(hand, pid)["solid"] = True  # (set by hand: not the water's)
    assert ops.find_entity(ops.set_water(hand, pid, opacity=0.5), pid)["solid"] is True, "kept"
    via_param = ops.find_entity(ops.set_behaviour_param(scene, pid, "WaterSurface", "passable", "block"), pid)
    assert via_param["solid"] is True and via_param["components"]["collider"]["kind"] == "box", "as set_water"
    back = ops.set_behaviour_param(ops.set_water(scene, pid, passable="block"), pid, "WaterSurface", "passable", "auto")
    assert "solid" not in ops.find_entity(back, pid)


def test_a_waded_pond_s_deep_basin_outside_its_outline_isn_t_its_water() -> None:
    """Only within its outline is it the pond's water: its box's corner, its basin dug deep past its edge, is dry."""
    scene = _room(pond={"passable": "wade", "wade_depth": 0.3, "shore": "terrain"})
    pid = ops.entities(scene)[0]["id"]
    ops.find_entity(scene, pid)["elevation"] = 0.0
    scene = ops.sculpt_terrain_stroke(scene, "flatten", [[1200, 300, 1.0]] * 6, radius=260, target=-24.0)
    world = _world(scene)
    assert not _stands(world, 1200, 300), "in it: 0.75 m, deeper than its 0.3 m"
    assert _stands(world, 1060, 220), "its box's corner, outside its outline: no water there (however deep the ground)"
