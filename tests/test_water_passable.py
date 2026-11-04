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
from engine.hd2d.world import DEEP, DEEP_SLACK, World, _surface

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


def _said(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """What FloorRoute says in the log (its logger doesn't propagate to pytest's capture)."""
    from engine.behaviours import floor_route

    said: list[str] = []
    monkeypatch.setattr(floor_route.logger, "warning", lambda msg, *args: said.append(msg % args))
    return said


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


def _uneven() -> dict[str, Any]:
    """A blocking pond shored by the sculpted ground, its bed uneven: two holes (the west one a pit too steep to climb
    out of, water or not) and an islet."""
    s = _room(pond={"walkable": False, "shore": "terrain"})
    ops.find_entity(s, ops.entities(s)[0]["id"])["elevation"] = -4.0
    s = ops.sculpt_terrain_stroke(s, "flatten", [[1200, 300, 1.0]], radius=80, target=-12.0)
    s = ops.sculpt_terrain_stroke(s, "flatten", [[1080, 300, 1.0]] * 4, radius=24, target=-40.0)
    s = ops.sculpt_terrain_stroke(s, "flatten", [[1250, 320, 1.0]] * 4, radius=20, target=-2.0)
    return ops.sculpt_terrain_stroke(s, "flatten", [[1300, 260, 1.0]] * 4, radius=30, target=-30.0)


def test_an_npc_with_no_way_out_is_stranded_said_once_and_doesn_t_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    """In blocking water at the bottom of a pit too steep to climb: no way out at all."""
    world = _world(_uneven())
    npc, route = _npc(world, 1082.0, 292.0, [[200.0, 800.0, 0.0]])
    calls = {"ways": 0}
    real = world.ways_out

    def counted(*args: Any, **kwargs: Any) -> Any:
        calls["ways"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(world, "ways_out", counted)
    said = _said(monkeypatch)
    for _ in range(60 * 12):
        route.update(1 / 60)
    assert npc.mesh_hd2d_stranded and "can't walk out of the water" in npc.mesh_hd2d_stranded
    assert sum("is stranded" in s for s in said) == 1, ("said once", said)
    assert calls["ways"] <= 3, ("looked for a way out at first and after each RETRY_S, not every frame", calls)
    assert abs(npc.center_x - 1082.0) < 24 and abs(npc.center_y - 310.0) < 24, "stayed in the pit (no teleport)"


def test_an_npc_far_out_in_blocking_water_walks_out_though_no_way_out_is_within_reach() -> None:
    """Re-review of bb320df: 8.75 m from the shore, no standing place within ways_out's 6 m: it still walks down the
    water's fall and out."""
    from engine.physics_runtime import _sprite_to_aabb

    scene = _room()
    scene, pid = ops.place_blank(scene, "start", "Big lake", 800.0, 300.0)
    scene = ops.set_water(scene, pid, preset="natural_pond", shape="ellipse", width=900.0, height=560.0,
                          passable="block")
    world = _world(scene)
    assert world.ways_out(800 / P, 300 / P, 0.0) == [], "no way out within reach"
    npc, route = _npc(world, 800.0, 300.0, [[200.0, 800.0, 0.0]])
    for _ in range(60 * 20):
        route.update(1 / 60)
    box = _sprite_to_aabb(npc)
    assert not getattr(npc, "mesh_hd2d_stranded", None)
    assert world.blocked(box.x / P, box.y / P, npc.mesh_entity_data["elevation"] / P) <= 0.0, "out"


def test_leaving_blocking_water_lends_no_deeper_wading_through_the_water_beyond() -> None:
    """Re-review of bb320df: one put in a blocking pond over a deep (auto) river's bank, pushed towards the river,
    took the pond's large values as its allowance and waded right across 0.8 m of water (auto's limit 0.5 m)."""
    from engine.physics_runtime import _sprite_to_aabb

    scene = _room()
    scene, pid = ops.place_blank(scene, "start", "Pond", 300.0, 720.0)
    scene = ops.set_water(scene, pid, preset="natural_pond", shape="ellipse", width=320.0, height=192.0,
                          passable="block")
    world = _world(scene)
    w = _Walker(center_x=300.0, center_y=718.0, width=32.0, height=48.0, scale_x=1.0,
                mesh_entity_data={"elevation": 0.0, "components": {"collider": {"kind": "box", "auto": True}}})
    assert world.blocked(300 / P, 700 / P, 0.0) > 0.0, "it starts in the pond"
    deepest = -1e9
    for _ in range(600):
        world.move(w, (0.0, -2.0), [])
        box = _sprite_to_aabb(w)
        z = w.mesh_entity_data["elevation"] / P
        deepest = max(deepest, world.excess(box.x / P, box.y / P, z, box.w / 2 / P, box.h / 2 / P, "wading"))
    box = _sprite_to_aabb(w)
    assert box.y > 560, ("never across the river", box.y)
    assert deepest <= DEEP_SLACK + 1e-9, ("never in water deeper than it may wade", deepest)


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
    for _ in range(100):
        world.move(walker, (0.0, -2.0), [])
    assert walker.center_y - 18 < 495.0, ("out by its near bank", walker.center_y)


def test_a_pond_on_a_raised_floor_doesn_t_block_the_ground_under_it() -> None:
    scene = _flat_room(passable="block")
    ops.entities(scene)[0]["elevation"] = 64.0  # (a roof pool, 2 m up)
    world = _world(scene)
    assert world.stand(800 / P, 600 / P, 0.0, 0.3, 0.19) is not None, "the ground under it: walked"


def test_a_wide_npc_judged_by_its_own_feet_plans_a_bounded_number_of_times_and_says_so_once(
        monkeypatch: pytest.MonkeyPatch) -> None:
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
    said = _said(monkeypatch)
    for _ in range(60 * 30):
        route.update(1 / 60)
    said = [s for s in said if "is stranded" in s or "can't get through" in s]
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


def test_in_blocking_water_only_steps_out_along_a_canal_a_river_or_round_a_rim() -> None:
    """Re-review of 82018f8: how far in it is, unchanged along a canal or a blocked river and nearly so round a
    pond's rim, let one put in it travel along it (and out somewhere far away). Each step must take it out."""
    def walker(x: float, y: float) -> _Walker:
        return _Walker(center_x=x, center_y=y + 18, width=32.0, height=48.0, scale_x=1.0,
                       mesh_entity_data={"elevation": 0.0, "components": {"collider": {"kind": "box", "auto": True}}})

    scene = {"entities": [], "settings": {"world_width": 1600, "world_height": 1200,
                                          "hd2d": {"ground": {"texture": "assets/textures/grass.png",
                                                              "from": [0, 0], "to": [1600, 1200]}}}}
    canal, pid = ops.place_blank(copy.deepcopy(scene), "start", "Canal", 800.0, 600.0)
    canal = ops.set_water(canal, pid, preset="natural_pond", shape="rect", width=1200.0, height=96.0, passable="block")
    world = _world(canal)
    w = walker(300.0, 600.0)  # (100 px in from its west end)
    for _ in range(600):
        world.move(w, (2.0, 0.0), [])
    assert w.center_x < 330.0, ("not along the canal", w.center_x)
    for _ in range(60):
        world.move(w, (0.0, 2.0), [])
    assert world.blocked(w.center_x / P, (w.center_y - 24) / P, 0.0) <= 0.0, "out by its near side"
    river_room = ops.add_river(copy.deepcopy(scene), "stream", [[4.0, 600.0, 192.0, 8.0], [1596.0, 600.0, 192.0, 8.0]],
                               passable="block")
    world = _world(river_room)
    w = walker(800.0, 640.0)
    for _ in range(600):
        world.move(w, (2.0, 0.0), [])
    assert w.center_x < 830.0, ("not along the blocked river", w.center_x)
    rim, pid = ops.place_blank(copy.deepcopy(scene), "start", "Lake", 800.0, 600.0)
    rim = ops.set_water(rim, pid, preset="natural_pond", shape="natural", seed=1, width=700.0, height=500.0,
                        passable="block")
    world = _world(rim)
    import math
    for deg in (240.0, 255.0, 300.0):
        w = walker(800.0, 600.0)
        # (just inside its rim on that bearing, pushed towards its middle and round it)
        for r in range(400, 0, -2):
            x, y = 800.0 + r * math.cos(math.radians(deg)), 600.0 + r * math.sin(math.radians(deg))
            if world.blocked(x / P, y / P, 0.0) > 0.0:
                break
        w.center_x, w.center_y = x, y + 24
        start = (w.center_x, w.center_y)
        for _ in range(300):
            world.move(w, (-2.0 * math.cos(math.radians(deg)), -2.0 * math.sin(math.radians(deg)) + 1.0), [])
        travelled = math.hypot(w.center_x - start[0], w.center_y - start[1])
        assert travelled < 40.0, ("not round its rim", deg, travelled)


def test_an_npc_put_just_inside_a_blocking_pond_walks_out_and_on() -> None:
    world = _world(_flat_room(passable="block"))
    for x, y in ((520.0, 600.0), (800.0, 430.0), (1060.0, 700.0)):  # (inside its west, north and south-east shores)
        npc, route = _npc(world, x, y, [[200.0, 1000.0, 0.0], [300.0, 1000.0, 0.0]])
        assert world.blocked(x / P, y / P, 0.0) > 0.0
        for _ in range(60 * 20):
            route.update(1 / 60)
        assert world.blocked(npc.center_x / P, (npc.center_y - 24) / P, 0.0) <= 0.0, ("out", x, y)
        assert not getattr(npc, "mesh_hd2d_stranded", None), ("not stranded", x, y)


def test_where_two_blocking_ponds_meet_no_one_is_held_and_an_npc_past_a_river_s_middle_walks_out() -> None:
    """Re-review of 1eb0144: where the larger of two blocking waters falls too gently for BLOCK_OUT (Lakeside's lake
    and its inlet), someone put there couldn't move; an NPC just past a blocked river's middle tried only the four
    nearest ways out, all across its middle."""
    import math

    from engine.physics_runtime import _sprite_to_aabb

    scene = _flat_room(passable="block")
    scene, second = ops.place_blank(scene, "start", "Inlet", 1060.0, 520.0)
    scene = ops.set_water(scene, second, preset="natural_pond", shape="ellipse", width=420.0, height=120.0,
                          rotation=25.0, passable="block")
    ops.find_entity(scene, second)["elevation"] = -8.0  # (its own level: the two waters' terms differ)
    world = _world(scene)
    held = []
    for sx in range(860, 1200, 20):
        for sy in range(440, 620, 20):
            if world.blocked(sx / P, sy / P, 0.0) <= 0.0:
                continue
            w = _Walker(center_x=float(sx), center_y=sy + 18.0, width=32.0, height=48.0, scale_x=1.0,
                        mesh_entity_data={"elevation": 0.0, "components": {"collider": {"kind": "box", "auto": True}}})
            for _ in range(400):  # (each frame the way its water falls fastest, as a player would find it)
                box = _sprite_to_aabb(w)  # (its feet box's middle: where the world measures it)
                x, y = box.x / P, box.y / P
                best = min((world.blocked(x + math.cos(a) * 0.06, y + math.sin(a) * 0.06, 0.0), a)
                           for a in (i * math.tau / 16 for i in range(16)))[1]
                world.move(w, (2.0 * math.cos(best), 2.0 * math.sin(best)), [])
                box = _sprite_to_aabb(w)
                if world.blocked(box.x / P, box.y / P, 0.0) <= 0.0:
                    break
            else:
                held.append((sx, sy))
    assert not held, ("held where the two waters meet", held[:5], len(held))
    river_world = _world(_room(river_args={"passable": "block"}))
    npc, route = _npc(river_world, 200.0, 599.0, [[200.0, 800.0, 0.0], [300.0, 800.0, 0.0]])
    for _ in range(60 * 20):
        route.update(1 / 60)
    assert not getattr(npc, "mesh_hd2d_stranded", None), "it walks out (the near bank, behind it)"
    box = _sprite_to_aabb(npc)
    assert river_world.blocked(box.x / P, box.y / P, npc.mesh_entity_data["elevation"] / P) <= 0


def _gets_out(world: World, x_px: float, y_px: float, frames: int = 500) -> bool:
    """Whether some one of eight steady directions (as a player holds one) takes one put at (x, y) out."""
    import math

    from engine.physics_runtime import _sprite_to_aabb

    z = _floor(world, x_px, y_px)
    for k in range(8):
        d = (2.0 * math.cos(k * math.pi / 4), 2.0 * math.sin(k * math.pi / 4))
        w = _Walker(center_x=float(x_px), center_y=y_px + 18.0, width=32.0, height=48.0, scale_x=1.0,
                    mesh_entity_data={"elevation": z * P,
                                      "components": {"collider": {"kind": "box", "auto": True}}})
        last = None
        for frame in range(frames):
            world.move(w, d, [])
            if frame % 10 == 9:  # (out, or stalled: no need to push on)
                box = _sprite_to_aabb(w)
                if world.blocked(box.x / P, box.y / P, w.mesh_entity_data["elevation"] / P) <= 0.0:
                    return True
                if (box.x, box.y) == last:
                    break
                last = (box.x, box.y)
    return False


def test_out_of_carved_narrow_and_uneven_blocking_water_some_way_always_leads() -> None:
    """Re-review of 1eb0144: in a carved blocked river, a narrow curved one and a terrain-shored pond with holes in
    its bed, the depth cap held one put past the river's middle (or over a hole) where only stepping out was
    allowed: no direction got them out. Here, from each of the starts that were held, one does."""
    carved = _world(_room(river_args={"passable": "block"}))
    scene: dict[str, Any] = {"entities": [], "settings": {"world_width": 1600, "world_height": 1200, "hd2d": {
        "ground": {"texture": "assets/textures/grass.png", "from": [0, 0], "to": [1600, 1200]}}}}
    scene = ops.add_river(scene, "n", [[4.0, 600.0, 24.0, -8.0], [700.0, 640.0, 24.0, -8.0],
                                       [1596.0, 560.0, 24.0, -8.0]], passable="block")
    narrow = _world(ops.carve_river_bed(scene, "n", depths=[0.3, 0.3, 0.3]))
    uneven = _world(_uneven())
    held = []
    for name, world, starts in (("carved", carved, ((160, 600), (200, 600), (200, 606), (520, 606))),
                                ("narrow", narrow, ((100, 606), (550, 636), (580, 642), (610, 636))),
                                ("uneven", uneven, ((1198, 296), (1198, 304), (1206, 296)))):  # (not the west hole: a pit too
                                # steep to climb out of with no water at all)
        for sx, sy in starts:
            assert world.blocked(sx / P, sy / P, _floor(world, sx, sy)) > 0.0, (name, sx, sy, "starts in it")
            if not _gets_out(world, sx, sy):
                held.append((name, sx, sy))
    assert not held, held


def test_an_npc_whose_route_point_can_t_be_reached_plans_again_once_a_second_not_every_frame(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """Re-review of 1eb0144: with no wait set, a point it can't reach (in blocking water) was planned for again every
    frame."""
    scene = _room()
    scene, pid = ops.place_blank(scene, "start", "Big lake", 800.0, 300.0)
    scene = ops.set_water(scene, pid, preset="natural_pond", shape="ellipse", width=900.0, height=560.0,
                          passable="block")
    world = _world(scene)
    npc, route = _npc(world, 200.0, 800.0, [[800.0, 300.0, 0.0]])  # (dry where it stands; its point in the lake)
    calls = {"path": 0}
    real = world.path

    def counted(*args: Any, **kwargs: Any) -> Any:
        calls["path"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(world, "path", counted)
    for _ in range(600):
        route.update(1 / 60)
    assert 1 <= calls["path"] <= 11, ("about once a second over 10 s", calls["path"])
    assert not getattr(npc, "mesh_hd2d_stranded", None), "it can stand: it isn't stranded, its point is just out of reach"


def test_where_a_lake_and_its_inlet_overlap_players_and_npcs_get_out_down_the_crease() -> None:
    """Re-review of 1eb0144 (Lakeside's lake and inlet, as built there): where two blocking waters overlap with their
    edges facing nearly opposite ways, the way out of both is a narrow crease. A player pushing roughly that way was
    held (each step slightly off it refused), and an NPC making for its listed ways out crept, gave each up and was
    reported stranded though out was there."""
    from engine.physics_runtime import _sprite_to_aabb

    scene: dict[str, Any] = {"entities": [], "settings": {"world_width": 2000, "world_height": 1400, "hd2d": {
        "ground": {"texture": "assets/textures/grass.png", "from": [0, 0], "to": [2000, 1400]}}}}
    scene, lake = ops.place_blank(scene, "start", "Lake", 1408.0, 992.0)
    scene = ops.set_water(scene, lake, preset="natural_pond", shape="natural", width=460.0, height=330.0,
                          passable="block")
    scene, inlet = ops.place_blank(scene, "start", "Inlet", 1168.0, 880.0)
    scene = ops.set_water(scene, inlet, preset="natural_pond", shape="natural", width=330.0, height=96.0,
                          rotation=25.0, passable="block")
    world = _world(scene)
    starts = ((1256, 922), (1262, 928), (1268, 934), (1250, 916))
    for sx, sy in starts:
        assert world.blocked(sx / P, sy / P, 0.0) > 0.0, (sx, sy, "starts in both")
    assert [s for s in starts if not _gets_out(world, *s)] == [], "a player gets out"
    stranded = []
    for sx, sy in starts:
        npc, route = _npc(world, float(sx), float(sy), [[300.0, 300.0, 0.0], [400.0, 300.0, 0.0]])
        for _ in range(60 * 12):
            route.update(1 / 60)
        box = _sprite_to_aabb(npc)
        if getattr(npc, "mesh_hd2d_stranded", None) or world.blocked(box.x / P, box.y / P, 0.0) > 0.0:
            stranded.append((sx, sy))
    assert stranded == [], "an NPC walks out"


def test_with_only_its_feet_s_edge_in_blocking_water_it_goes_no_further_in() -> None:
    """Re-review of bb320df: once its middle is out of blocking water, the rest of its feet may only come out."""
    from engine.physics_runtime import _sprite_to_aabb

    scene = _room()
    scene, pid = ops.place_blank(scene, "start", "Pond", 300.0, 720.0)
    scene = ops.set_water(scene, pid, preset="natural_pond", shape="ellipse", width=320.0, height=192.0,
                          passable="block")  # (its south edge at y 816)
    world = _world(scene)
    w = _Walker(center_x=300.0, center_y=820.0 + 18.0, width=32.0, height=48.0, scale_x=1.0,
                mesh_entity_data={"elevation": 0.0, "components": {"collider": {"kind": "box", "auto": True}}})
    box = _sprite_to_aabb(w)
    half = (box.w / 2 / P, box.h / 2 / P)
    start = world.excess(box.x / P, box.y / P, 0.0, *half, "blocking")
    assert world.blocked(box.x / P, box.y / P, 0.0) <= 0.0 < start, "its middle out, its edge in"
    for _ in range(120):
        world.move(w, (0.0, -2.0), [])  # (pushing into the pond)
        box = _sprite_to_aabb(w)
        assert world.blocked(box.x / P, box.y / P, 0.0) <= 0.0, "its middle never in"
        assert world.excess(box.x / P, box.y / P, 0.0, *half, "blocking") <= start + 1e-9, "never further in"
