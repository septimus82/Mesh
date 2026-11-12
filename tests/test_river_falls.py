"""M17-W1: waterfalls on rivers, headless.

- A river's ``falls`` mark the stretch from a control point (its lip) to the next (its foot) as falling water: stored
  plainly (``{"from": i}``, its foam and spray only where they differ), read back the same; older rivers gain no key.
- Its surface follows a falling jet's curve: level at the lip (the water leaves it smoothly), steepest at the foot,
  with a sample exactly at each; it is drawn as a curtain of rows down that curve (``fall_vertices``), not as ribbon.
- Refusals name the waterfall and say what to change; nothing is written: a drop under 0.5 m or over 16 m, gentler
  than half a metre a metre, turning more than 20 degrees, the first or last stretch, next to another, more than a
  room holds. Rooms with waterfalls flowing into a pond: the foot may be in it, the top may not.
- Falling water blocks whatever the river's ``passable`` (nobody stands in it or walks off the lip over it); routes go
  round it; carving digs the pool under it and keeps the cliff beside it; sinking never measures a fall.
- The project ops (``set_waterfall``, ``remove_waterfall``; ``falls`` on ``add_river``/``set_river``) are checked
  whole; Studio's review lines say it in words.
The real window (the curtain drawn, animated and occluded, foam, spray, Studio, Play, export) is
tests/test_river_falls_gpu.py."""

from __future__ import annotations

import copy
import json
import math
from typing import Any

import pytest

from engine import authoring
from engine import project_ops as ops
from engine.hd2d import river
from engine.hd2d.settings import parse_hd2d
from engine.hd2d.world import World

pytestmark = pytest.mark.fast

P = 32.0
# a 3 m stream in a channel 0.5 m under the ground, falling 1.5 m from point 3 to point 4 (a 1.25 m run)
COURSE = [[640.0, 100.0, 96.0, -16.0], [640.0, 400.0, 96.0, -16.0], [640.0, 612.0, 96.0, -16.0],
          [640.0, 652.0, 96.0, -64.0], [640.0, 1000.0, 96.0, -64.0]]


def _room(points: list[list[float]] = COURSE, falls: Any = ({"from": 2},), **river_args: Any) -> dict[str, Any]:
    scene = {"entities": [], "settings": {"world_width": 1600, "world_height": 1200,
                                          "hd2d": {"ground": {"texture": "assets/textures/grass.png",
                                                              "from": [0, 0], "to": [1600, 1200]}}}}
    args = {"falls": [dict(f) for f in falls]} if falls else {}
    return ops.add_river(scene, "brook", points, **args, **river_args)


def _river(scene: dict[str, Any]) -> river.River:
    return river.parse_rivers(scene["settings"]["hd2d"]["rivers"])[0]


def test_a_waterfall_is_stored_plainly_and_read_back_the_same() -> None:
    scene = _room()
    assert ops.rivers(scene)[0]["falls"] == [{"from": 2}], "defaults aren't stored"
    r = _river(scene)
    assert r.falls == (river.Fall(2, 0.6, 0.4),)
    assert river.to_json(river.parse_river(river.to_json(r))) == river.to_json(r), "stored as read"
    tuned = ops.set_waterfall(scene, "brook", 2, foam=0.25, spray=0.0)
    assert ops.rivers(tuned)[0]["falls"] == [{"from": 2, "foam": 0.25, "spray": 0.0}]
    plain = ops.remove_waterfall(tuned, "brook", 2)
    assert "falls" not in ops.rivers(plain)[0], "none left: no key, as older rivers have"
    assert ops.rivers(plain)[0] == ops.rivers(_room(falls=()))[0]
    again = ops.set_waterfall(plain, "brook", 2)
    assert ops.rivers(again) == ops.rivers(scene)


def test_its_surface_leaves_the_lip_level_and_lands_at_the_foot_steepest() -> None:
    r = _river(_room())
    rib = river.ribbon(r)
    ((lip, foot),) = rib.falls
    assert rib.u[lip] == rib.marks[2] and rib.u[foot] == rib.marks[3], "a sample exactly at the lip and the foot"
    top, low = -16.0 / P, -64.0 / P
    assert rib.level[lip] == pytest.approx(top) and rib.level[foot] == pytest.approx(low)
    run = rib.u[foot] - rib.u[lip]
    for k in range(lip, foot + 1):
        f = (rib.u[k] - rib.u[lip]) / run
        assert rib.level[k] == pytest.approx(top - (top - low) * f * f, abs=1e-9), "a jet's curve"
    assert all(a >= b for a, b in zip(rib.level, rib.level[1:])), "it only falls"
    first = (rib.level[lip] - rib.level[lip + 1]) / (rib.u[lip + 1] - rib.u[lip])
    last = (rib.level[foot - 1] - rib.level[foot]) / (rib.u[foot] - rib.u[foot - 1])
    assert first < 0.6 * last, ("it leaves the lip gently and lands steeply", first, last)
    steps = [b - a for a, b in zip(rib.u, rib.u[1:])]
    assert min(steps) > 0.09 and max(steps) < 0.4, "the regular samples moved, none crowded"


def test_older_rivers_and_other_rivers_are_sampled_as_before() -> None:
    plain = river.ribbon(_river(_room(falls=(), points=[[640.0, 100.0, 96.0, -16.0], [640.0, 1000.0, 96.0, -64.0]])))
    steps = {round(b - a, 9) for a, b in zip(plain.u, plain.u[1:])}
    assert len(steps) == 1 and plain.falls == (), "evenly sampled, as before"
    scene = _room()
    scene = ops.add_river(scene, "other", [[200.0, 100.0, 64.0, 0.0], [200.0, 900.0, 64.0, 0.0]])
    rivers = river.parse_rivers(scene["settings"]["hd2d"]["rivers"])
    alone = river.parse_rivers([ops.rivers(scene)[1]])
    assert river.ribbon(rivers[1]) == river.ribbon(alone[0]), "a waterfall on one river changes no other"
    data, idx, feet = river.fall_vertices(alone, 0.035)
    assert not data and not idx and not feet, "no waterfall: nothing for the GPU"


def test_refusals_name_the_waterfall_say_what_to_change_and_write_nothing() -> None:
    scene = _room()
    before = json.dumps(scene, sort_keys=True)
    cases = [
        ({"falls": [{"from": 0}]}, "needs water above and below it"),
        ({"falls": [{"from": 3}]}, "needs water above and below it"),
        ({"falls": [{"from": 2}, {"from": 2}]}, "ordinary water between them"),
        ({"falls": [{"from": 2, "foam": 1.5}]}, "foam must be a number from 0 to 1"),
        ({"falls": [{"from": 2, "mist": 1}]}, "unknown keys: mist"),
        ({"falls": [{"from": "2"}]}, "control point's number"),
        ({"falls": {"from": 2}}, "must be a list of waterfalls"),
    ]
    for change, words in cases:
        with pytest.raises(ops.OpError, match=words):
            ops.set_river(scene, "brook", **change)
    small = [list(p) for p in COURSE]
    small[3][3] = -16.0 - 8.0  # a quarter metre
    with pytest.raises(ops.OpError, match="from point 3 to 4 .* drops 0.25 m: a waterfall drops at least 0.5 m"):
        ops.set_river(scene, "brook", points=small)
    tall = [list(p) for p in COURSE]
    tall[3][3] = tall[4][3] = -16.0 - 17 * P
    with pytest.raises(ops.OpError, match="drops 17.0 m: a waterfall drops at most 16 m"):
        ops.set_river(scene, "brook", points=tall)
    gentle = [list(p) for p in COURSE]
    gentle[3][1] = 612.0 + 5 * P  # 1.5 m over 5 m
    with pytest.raises(ops.OpError, match="too gentle for a waterfall"):
        ops.set_river(scene, "brook", points=gentle)
    bent = [[640.0, 100.0, 64.0, -16.0], [640.0, 400.0, 64.0, -16.0], [640.0, 612.0, 64.0, -16.0],
            [690.0, 680.0, 64.0, -96.0], [900.0, 700.0, 64.0, -96.0]]
    with pytest.raises(ops.OpError, match="turns .* degrees as it falls"):
        ops.add_river(_room(falls=()), "bent", bent, falls=[{"from": 2}])
    uphill = [list(p) for p in COURSE]
    uphill[3][3] = 0.0
    with pytest.raises(ops.OpError, match="uphill"):
        ops.set_river(scene, "brook", points=uphill)
    with pytest.raises(ops.OpError, match="has no river 'nope'"):
        ops.set_waterfall(scene, "nope", 2)
    with pytest.raises(ops.OpError, match="has no waterfall from point 1"):
        ops.remove_waterfall(scene, "brook", 1)
    with pytest.raises(ops.OpError, match="counted from 0"):
        ops.set_waterfall(scene, "brook", True)
    assert json.dumps(scene, sort_keys=True) == before, "refused: nothing written"


def test_a_room_holds_at_most_eight_and_points_renumbered_need_their_falls() -> None:
    scene = _room(falls=())
    for k in range(4):  # four rivers, two falls each (eight): a ninth is refused
        x = (100.0, 300.0, 900.0, 1100.0)[k]
        course = [[x, 100.0, 64.0, 0.0], [x, 200.0, 64.0, 0.0], [x, 240.0, 64.0, -32.0], [x, 400.0, 64.0, -32.0],
                  [x, 440.0, 64.0, -64.0], [x, 600.0, 64.0, -64.0]]
        scene = ops.add_river(scene, f"r{k}", course, falls=[{"from": 1}, {"from": 3}])
    with pytest.raises(ops.OpError, match="at most 8 waterfalls"):
        ops.set_waterfall(scene, "brook", 2)
    plain = _room()
    longer = [*COURSE[:1], [640.0, 250.0, 96.0, -16.0], *COURSE[1:]]
    with pytest.raises(ops.OpError, match="give its falls too"):
        ops.set_river(plain, "brook", points=longer)
    moved = ops.set_river(plain, "brook", points=longer, falls=[{"from": 3}])
    assert ops.rivers(moved)[0]["falls"] == [{"from": 3}]
    assert ops.set_river(plain, "brook", flow=2.0)["settings"]["hd2d"]["rivers"][0]["falls"] == [{"from": 2}]


def test_it_is_drawn_as_a_curtain_down_the_curve_not_as_ribbon() -> None:
    r = _river(_room(flow=1.5))
    rib = river.ribbon(r)
    ((lip, foot),) = rib.falls
    _data, idx = river.vertices((r,), 0.035)
    quads = {i // 2 for i in idx}  # (each quad's first vertex pair is its sample)
    assert not any(lip <= k < foot for k in {min(v // 2 for v in idx[q:q + 6]) for q in range(0, len(idx), 6)})
    assert quads, "the rest of the river is drawn"
    data, cidx, feet = river.fall_vertices((r,), 0.035)
    n = river.FALL_FLOATS
    rows = len(data) // n // 2
    assert rows >= 9 and len(cidx) == (rows - 1) * 6
    z = [data[k * n + 2] for k in range(0, rows * 2, 2)]
    assert z[0] == pytest.approx(-16.0 / P + 0.035) and z[-1] == pytest.approx(-64.0 / P + 0.035)
    along = [data[k * n + 5] for k in range(0, rows * 2, 2)]
    assert all(b > a for a, b in zip(along, along[1:])), "down the curtain"
    flight = [data[k * n + 7] for k in range(0, rows * 2, 2)]
    assert flight[0] == 0.0 and flight[-1] == pytest.approx(math.sqrt(2 * 1.5 / river.GRAVITY)), "its time falling"
    assert data[6] == pytest.approx(-1.5) and data[n + 6] == pytest.approx(1.5), "across: its banks"
    ((fx, fy, low, half, tx, ty, foam, spray, drop, _seed),) = feet
    assert (fx * P, fy * P) == pytest.approx((640.0, 652.0), abs=0.5) and low == pytest.approx(-2.0)
    assert (half, foam, spray, drop) == pytest.approx((1.5, 0.6, 0.4, 1.5)) and ty > 0.99


def test_falling_water_blocks_whatever_passable_and_nobody_walks_off_the_lip_over_it() -> None:
    for passable in ("auto", "wade"):
        scene = _room(passable=passable, **({"wade_depth": 1.5} if passable == "wade" else {}))
        scene = ops.carve_river_bed(scene, "brook", depths=[0.4] * len(COURSE))
        world = World(parse_hd2d(scene["settings"]["hd2d"]), {})
        index = world.rivers
        assert index.falling_at(20.0, 632 / P) and not index.falling_at(20.0, 500 / P)
        assert not index.falling_at(20.0, 800 / P) and not index.falling_at(17.0, 632 / P)
        terrain = world.terrain

        def floor(x: float, y: float) -> float:
            return terrain.surface_at(x, y)[0] / P

        assert world.stand(20.0, 500 / P, floor(640, 500), 0.2, 0.2) is not None, "the stream above: waded"
        assert world.stand(20.0, 800 / P, floor(640, 800), 0.2, 0.2) is not None, "the pool below: waded"
        assert world.stand(20.0, 640 / P, floor(640, 640), 0.2, 0.2) is None, ("under the fall", passable)
        assert world.stand(20.0, 620 / P, -16.0 / P - 0.4, 0.2, 0.2) is None, "off the lip: no floor up there"
        assert world.excess(20.0, 632 / P, floor(640, 632), 0.2, 0.2, "blocking") > 0.0, "blocking, by its depth"
        route = world.path((18.0, 500 / P, floor(576, 500)), (18.0, 800 / P, floor(576, 800)))
        assert not any(index.falling_at(x, y) for x, y, _z in route), "routes go round it"
    # a short fall (0.5 m) in water waded to 1.5 m: not too deep anywhere, the falling water alone blocks
    short = [list(p) for p in COURSE]
    short[3][3] = short[4][3] = -32.0
    short[3][1] = 636.0  # (0.75 m on)
    scene = ops.carve_river_bed(_room(points=short, passable="wade", wade_depth=1.5), "brook", depths=[0.4] * 5)
    world = World(parse_hd2d(scene["settings"]["hd2d"]), {})
    bed = world.terrain.surface_at(640, 626)[0] / P
    assert world.deepest(20.0, 626 / P, bed, 0.2, 0.2) < 1.5, "not too deep to wade"
    assert world.stand(20.0, 626 / P, bed, 0.2, 0.2) is None, "under a short fall: blocked by its falling water"
    assert world.stand(20.0, 800 / P, world.terrain.surface_at(640, 800)[0] / P, 0.2, 0.2) is not None


def _glen() -> dict[str, Any]:
    """Ground sculpted into a 3 m plateau (y < 630 px) over a cliff, a stream falling from its edge."""
    scene = _room(falls=())
    scene["settings"]["hd2d"].pop("rivers")
    dabs = [[float(x), float(y), 1.0] for y in range(0, 577, 64) for x in range(320, 961, 64)]
    scene = ops.sculpt_terrain_stroke(scene, "flatten", dabs, radius=96.0, target=96.0)
    edge = [[float(x), y, 1.0] for x in range(320, 961, 12) for y in (606.0, 618.0)]
    scene = ops.sculpt_terrain_stroke(scene, "flatten", edge, radius=18.0, target=96.0)
    foot = [[float(x), y, 1.0] for x in range(320, 961, 12) for y in (648.0, 662.0)]
    scene = ops.sculpt_terrain_stroke(scene, "flatten", foot, radius=18.0, target=0.0)
    course = [[640.0, 100.0, 96.0, 92.0], [640.0, 400.0, 96.0, 92.0], [640.0, 612.0, 96.0, 92.0],
              [640.0, 676.0, 96.0, 0.0], [640.0, 1000.0, 96.0, 0.0]]
    return ops.add_river(scene, "brook", course, falls=[{"from": 2}])


def test_carving_digs_the_pool_under_the_fall_and_keeps_the_cliff_beside_it() -> None:
    scene = _glen()
    carved = ops.carve_river_bed(scene, "brook", depths=[0.4] * 5)
    h0 = World(parse_hd2d(scene["settings"]["hd2d"]), {}).terrain
    h1 = World(parse_hd2d(carved["settings"]["hd2d"]), {}).terrain
    for y in (630.0, 640.0, 650.0):  # the cliff's face beside the fall: as it was sculpted
        for x in (640.0 - 96.0, 640.0 + 96.0):
            assert h1.height(x, y) == h0.height(x, y), (x, y)
    r = _river(carved)
    low = r.points[3][3]
    assert h1.height(640.0, 650.0) == pytest.approx(low - 0.4 * P, abs=2.0), "under the fall: its pool"
    assert h1.height(640.0, 500.0) < h0.height(640.0, 500.0), "the stream above: its bed"


def test_sinking_never_measures_falling_water() -> None:
    scene = _glen()
    r = _river(scene)
    terrain = World(parse_hd2d(scene["settings"]["hd2d"]), {}).terrain
    lowered = river.sunk(terrain, r)
    assert lowered.points[2][3] >= r.points[2][3] - 6.5, "the lip sinks with the stream above, not the cliff below"
    assert lowered.points[2][3] - lowered.points[3][3] >= river.FALL_DROP_PX[0], "still a waterfall"


def test_a_waterfall_may_fall_into_a_pond_but_its_top_stays_on_the_land() -> None:
    def room(lip_y: float) -> dict[str, Any]:
        scene = _room(falls=())
        scene["settings"]["hd2d"].pop("rivers")
        scene, pond = ops.place_blank(scene, "start", "Pool", 640.0, 820.0)
        scene = ops.set_water(scene, pond, preset="natural_pond", shape="ellipse", width=480.0, height=320.0)
        ops.find_entity(scene, pond)["elevation"] = -64.0
        course = [[640.0, 100.0, 96.0, -16.0], [640.0, 400.0, 96.0, -16.0], [640.0, lip_y, 96.0, -16.0],
                  [640.0, lip_y + 48.0, 96.0, -64.0], [640.0, 820.0, 96.0, -64.0]]
        return ops.add_river(scene, "brook", course, falls=[{"from": 2}], mouth="auto")

    scene = room(640.0)  # its shore at y 660: the foot (688) in the pond
    (r,) = river.parse_rivers(scene["settings"]["hd2d"]["rivers"])
    mouth = river.join(r, river.ponds_of(scene["entities"]))
    rib = river.ribbon(r)
    assert mouth.fall_u == pytest.approx(rib.u[rib.falls[0][1]]), "eased into the pond only below the fall"
    with pytest.raises(ops.OpError, match="has its top over the pond"):
        room(700.0)


def test_studio_review_says_it_in_words_and_the_loader_keeps_a_broken_one_out() -> None:
    plain = _room(falls=())
    lines = authoring._river_lines("start", ops.rivers(plain), ops.rivers(ops.set_waterfall(plain, "brook", 2)))
    assert lines == ["start: changes river 'brook' (waterfall from point 3 to 4)"]
    lines = authoring._river_lines("start", ops.rivers(_room()), ops.rivers(plain))
    assert lines == ["start: changes river 'brook' (no waterfalls now)"]
    added = authoring._river_lines("start", [], ops.rivers(ops.set_waterfall(_room(), "brook", 2, spray=0.0)))
    assert added == ["start: adds river 'brook' (5 points, flowing 1 m/s; waterfall from point 3 to 4 (spray 0))"]
    broken = copy.deepcopy(_room()["settings"]["hd2d"])
    broken["rivers"][0]["falls"] = [{"from": 9}]
    parsed = parse_hd2d(broken, lenient=True)
    assert parsed.rivers == () and "needs water above and below it" in (parsed.rivers_error or "")
