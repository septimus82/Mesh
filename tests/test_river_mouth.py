"""#461 R4: rivers flowing into ponds, round ends and sinking along the whole river, headless.

- ``mouth: "auto"`` joins a river to the pond its last point lies in (``river.join``), or is refused, saying what to
  change: no pond there, its end not wholly in it, its course crossing the pond's shore twice, its water not within
  5 cm of the pond's. Nothing is moved to fit; older rivers and ponds are as they were.
- What is drawn is what is water: ``RiverIndex`` has none of a joined river's water in its pond, nor past a round
  end; carving makes a round end a bowl, and never digs a trough past it.
- Sinking measures the ground beside the river every quarter metre (a dip between two points is found), never the
  bed of a pond or another river beside it, and never takes a river below the pond it flows into.
The real window (drawn coverage, Studio, Play, export) is tests/test_river_mouth_gpu.py."""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from engine import project_ops as ops
from engine.hd2d import river
from engine.hd2d.settings import parse_hd2d
from engine.hd2d.terrain import Terrain
from engine.hd2d.world import World

pytestmark = pytest.mark.fast

P = 32.0
POND = {"x": 1200.0, "y": 600.0, "width": 480.0, "height": 320.0}  # px: x 960..1440, y 440..760
# a 3 m stream flowing east from the room's west edge into the pond, at the pond's level
STREAM = [[4.0, 600.0, 96.0, 0.0], [640.0, 610.0, 96.0, 0.0], [1150.0, 600.0, 96.0, 0.0]]


def _room(points: list[list[float]] = STREAM, *, level: float = 0.0, **river_args: Any) -> dict[str, Any]:
    scene = {"entities": [], "settings": {"world_width": 1600, "world_height": 1200,
                                          "hd2d": {"ground": {"texture": "assets/textures/grass.png",
                                                              "from": [0, 0], "to": [1600, 1200]}}}}
    scene, pond = ops.place_blank(scene, "start", "Lake", POND["x"], POND["y"])
    scene = ops.set_water(scene, pond, preset="natural_pond", shape="ellipse", width=POND["width"],
                          height=POND["height"])
    ops.find_entity(scene, pond)["elevation"] = level
    return ops.add_river(scene, "stream", points, **river_args)


def _rivers(scene: dict[str, Any]) -> tuple[river.River, ...]:
    return river.parse_rivers(scene["settings"]["hd2d"]["rivers"])


def _index(scene: dict[str, Any]) -> river.RiverIndex:
    return river.RiverIndex(_rivers(scene), river.ponds_of(scene["entities"]))


def test_a_river_joins_the_pond_its_last_point_lies_in_and_is_stored_plainly() -> None:
    plain = _room()
    assert ops.rivers(plain) == [{"id": "stream", "points": STREAM}], "older and plain rivers: no new keys"
    joined = ops.set_river(plain, "stream", mouth="auto")
    assert ops.rivers(joined) == [{"id": "stream", "points": STREAM, "mouth": "auto"}]
    (r,) = _rivers(joined)
    mouth = river.join(r, river.ponds_of(joined["entities"]))
    assert mouth.pond.id == ops.entities(joined)[0]["id"]
    assert mouth.at[0] * P == pytest.approx(960.0, abs=2.0), "where its middle crosses the shore"
    assert mouth.tangent[0] == pytest.approx(1.0, abs=0.01) and mouth.half == pytest.approx(1.5, abs=0.01)
    assert river.to_json(river.parse_river(river.to_json(r))) == river.to_json(r), "stored as read"
    assert ops.set_river(joined, "stream", mouth="none")["settings"] == plain["settings"], "off: as before"
    with pytest.raises(ops.OpError, match="mouth must be one of"):
        ops.set_river(plain, "stream", mouth="lake")
    with pytest.raises(ops.OpError, match="ends must be one of"):
        ops.set_river(plain, "stream", ends="pointy")


def test_refusals_say_what_to_change_and_change_nothing() -> None:
    plain = _room()
    before = json.dumps(plain, sort_keys=True)
    short = [[4.0, 600.0, 96.0, 0.0], [640.0, 610.0, 96.0, 0.0], [900.0, 600.0, 96.0, 0.0]]
    with pytest.raises(ops.OpError, match="isn't in one: move it into a pond's water"):
        ops.set_river(plain, "stream", points=short, mouth="auto")
    wide = [[100.0, 600.0, 96.0, 0.0], [640.0, 560.0, 96.0, 0.0], [975.0, 600.0, 192.0, 0.0]]  # its end on the shore
    with pytest.raises(ops.OpError, match="isn't wholly in the pond"):
        ops.set_river(plain, "stream", points=wide, mouth="auto")
    with pytest.raises(ops.OpError, match=r"0\.25 m above its water"):
        ops.set_river(_room(level=-8.0), "stream", mouth="auto")
    with pytest.raises(ops.OpError, match=r"0\.25 m below its water"):
        ops.set_river(_room(level=8.0), "stream", mouth="auto")
    assert json.dumps(plain, sort_keys=True) == before, "nothing moved, relevelled or written"


def test_a_course_in_and_out_of_the_pond_and_one_flowing_out_of_it_are_refused() -> None:
    # in through the pond's north shore, out again, and back in: two crossings
    twice = [[40.0, 300.0, 64.0, 0.0], [600.0, 420.0, 64.0, 0.0], [1050.0, 500.0, 64.0, 0.0], [1250.0, 410.0, 64.0, 0.0],
             [1400.0, 600.0, 64.0, 0.0]]
    with pytest.raises(ops.OpError, match="crosses the pond '.*''s shore more than once"):
        ops.set_river(_room(), "stream", points=twice, mouth="auto")
    # downstream order: rising in the pond and flowing out, its last point on dry ground
    out = [[1150.0, 600.0, 96.0, 0.0], [1350.0, 800.0, 96.0, 0.0], [1500.0, 1000.0, 96.0, 0.0]]
    with pytest.raises(ops.OpError, match="isn't in one"):
        ops.set_river(_room(), "stream", points=out, mouth="auto")


def test_an_angled_join_and_two_ponds_at_their_own_levels() -> None:
    angled = [[300.0, 1100.0, 64.0, 0.0], [800.0, 900.0, 64.0, 0.0], [1150.0, 640.0, 64.0, 0.0]]
    scene = ops.set_river(_room(angled), "stream", mouth="auto")
    mouth = river.join(_rivers(scene)[0], river.ponds_of(scene["entities"]))
    assert 0.3 < -mouth.tangent[1] < 0.95, "it enters at a slant"
    scene, high = ops.place_blank(scene, "start", "High pool", 300.0, 300.0)
    scene = ops.set_water(scene, high, preset="natural_pond", shape="ellipse", width=320.0, height=240.0)
    ops.find_entity(scene, high)["elevation"] = 40.0
    hill = [[1560.0, 100.0, 64.0, 60.0], [800.0, 200.0, 64.0, 40.0], [330.0, 300.0, 64.0, 40.0]]
    scene = ops.add_river(scene, "hill_stream", hill, mouth="auto")
    joined, problems = river.mouths(_rivers(scene), river.ponds_of(scene["entities"]))
    assert problems == {} and joined["hill_stream"].pond.id == high and joined["stream"].pond.id != high


def test_the_water_is_where_it_is_drawn_none_of_it_in_the_pond_none_past_a_round_end() -> None:
    free = _index(_room(ends="round"))
    joined = _index(ops.set_river(_room(ends="round"), "stream", mouth="auto"))
    deep_in_pond = (1100.0 / P, 600.0 / P)
    assert free.level_at(*deep_in_pond) is not None, "a free river's water lies over the pond's (two layers)"
    assert joined.level_at(*deep_in_pond, in_ponds=False) is None, "joined: the pond's water is there, not the river's"
    assert joined.level_at(*deep_in_pond) == (0.0, "stream"), "(its channel still water, at the pond's level)"
    assert joined.level_at(940.0 / P, 600.0 / P) is not None, "short of the shore: the river's"
    # its source rounded: the middle of its end is water, the square end's corners aren't
    assert joined.level_at(5.0 / P, 600.0 / P) is not None
    assert joined.level_at(6.0 / P, 646.0 / P) is None and joined.level_at(6.0 / P, 554.0 / P) is None
    square = _index(_room())
    assert square.level_at(6.0 / P, 646.0 / P) is not None, "square (as before R4): the corner is water"
    # a free end rounded too
    short = [[4.0, 600.0, 96.0, 0.0], [640.0, 610.0, 96.0, 0.0], [900.0, 600.0, 96.0, 0.0]]
    end = _index(_room(short, ends="round_end"))
    assert end.level_at(898.0 / P, 600.0 / P) is not None and end.level_at(898.0 / P, 646.0 / P) is None
    assert end.level_at(6.0 / P, 646.0 / P) is not None, "its source square"
    world = World(parse_hd2d(_room(ends="round")["settings"]["hd2d"]),
                  {}, river.ponds_of(ops.set_river(_room(ends="round"), "stream", mouth="auto")["entities"]))
    assert world.rivers.level_at(*deep_in_pond) is not None, "(the World's rivers: what the room's settings say)"


def test_carving_a_round_end_makes_a_bowl_and_no_trough_past_it() -> None:
    short = [[200.0, 600.0, 96.0, -16.0], [640.0, 610.0, 96.0, -16.0], [900.0, 600.0, 96.0, -16.0]]
    square = ops.carve_river_bed(_room(short), "stream")
    rounded = ops.carve_river_bed(_room(short, ends="round"), "stream")
    t_sq, t_rd = (Terrain.from_ground(parse_hd2d(s["settings"]["hd2d"]).ground) for s in (square, rounded))
    corner = (204.0, 644.0)  # just in from the source's square corner
    middle = (248.0, 600.0)  # the middle of its half circle
    assert t_sq.height(*corner) < -16.0, "square: its bed reaches the corner"
    assert t_rd.height(*corner) >= -16.0, "round: the corner is bank, dry (no trough past the half circle)"
    assert t_rd.height(*middle) < -16.0 - 20.0, "the end's middle: its full depth"
    assert t_rd.height(150.0, 600.0) > -16.0, "past the end: bank, rising"
    for s in (square, rounded):
        with pytest.raises(ops.OpError, match="already carved"):
            ops.carve_river_bed(s, "stream")


def test_sinking_finds_a_dip_between_points_and_keeps_a_mouth_at_its_pond() -> None:
    # water drawn over flat ground (0.25 m above), with a dip beside it halfway between two points
    over = [[4.0, 600.0, 96.0, 8.0], [800.0, 600.0, 96.0, 8.0], [1590.0, 600.0, 96.0, 8.0]]
    scene = ops.sculpt_terrain_stroke(_room(over), "lower", [[400, 680, 24], [400, 520, 24]], radius=40)
    t = Terrain.from_ground(parse_hd2d(scene["settings"]["hd2d"]).ground)
    (r,) = _rivers(scene)
    sunk = river.sunk(t, r, river.ponds_of(scene["entities"]))
    rib = river.ribbon(r)  # (half a metre and a terrain cell out from each bank, at each sample: every quarter metre)
    out = 48.0 + 16.0 + t.cell
    dip = min(min(t.height(c[0] * P, 600 + out), t.height(c[0] * P, 600 - out)) for c in rib.centre
              if 350 < c[0] * P < 450)
    assert dip < -16.0, "the dip, between its points: R3 measured only at the points (flat ground there)"
    assert max(p[3] for p in sunk.points) <= dip - river.SINK_M * P + 0.01, "under the dip, all along that stretch"
    assert river.sunk(t, sunk, river.ponds_of(scene["entities"])) is sunk, "sinking twice is sinking once"
    # flowing into a pond whose level is the ground's: never below the pond (it must meet its water)
    into = [[4.0, 600.0, 96.0, 8.0], [640.0, 610.0, 96.0, 8.0], [900.0, 605.0, 96.0, 0.0], [1150.0, 600.0, 96.0, 0.0]]
    scene = _room(into, mouth="auto")
    carved = ops.carve_river_bed(ops.sculpt_terrain_stroke(scene, "lower", [[940, 660, 24]], radius=40), "stream")
    (r,) = _rivers(carved)
    assert min(p[3] for p in r.points) >= 0.0 and river.join(r, river.ponds_of(carved["entities"])).pond


def test_carving_beside_a_pond_or_another_river_measures_their_shore_not_their_bed() -> None:
    a = [[4.0, 600.0, 96.0, -16.0], [1596.0, 600.0, 96.0, -16.0]]
    b = [[4.0, 708.0, 96.0, 8.0], [1596.0, 708.0, 96.0, 8.0]]  # 0.375 m apart, drawn over the ground
    scene = {"entities": [], "settings": {"world_width": 1600, "world_height": 1200,
                                          "hd2d": {"ground": {"texture": "assets/textures/grass.png",
                                                              "from": [0, 0], "to": [1600, 1200]}}}}
    scene = ops.add_river(ops.add_river(scene, "a", a), "b", b)
    scene = ops.carve_river_bed(scene, "a", depths=[1.2, 1.2])
    once = ops.carve_river_bed(scene, "b")
    (_a, b_sunk) = _rivers(once)
    assert b_sunk.points[0][3] == pytest.approx(-river.SINK_M * P, abs=0.01), "sunk under its own bank, not a's bed"
    with pytest.raises(ops.OpError, match="already carved"):
        ops.carve_river_bed(once, "b")


def test_older_rivers_draw_as_before_and_a_room_s_mouths_are_bounded() -> None:
    (r,) = _rivers(_room())
    data, idx = river.vertices((r,), 0.035)
    f = river.FLOATS_PER_VERTEX
    rib = river.ribbon(r)
    assert len(data) == 2 * len(rib.centre) * f and len(idx) == 6 * (len(rib.centre) - 1)
    assert tuple(data[21:25]) == (0.0, 0.0, pytest.approx(rib.u[-1]), -1.0), "square ends, no mouth"
    assert not _index(_room())._ends, "nothing set aside: its water as R3 had it"
    many = [{"id": f"r{i}", "points": [[4.0 + 0 * i, 40.0 + 120 * i, 32.0, 0.0], [600.0, 40.0 + 120 * i, 32.0, 0.0]],
             "mouth": "auto"} for i in range(river.MAX_MOUTHS + 1)]
    with pytest.raises(river.RiverError, match="at most 8 rivers flowing into ponds"):
        river.parse_rivers(many)


def test_a_pond_moved_away_leaves_the_river_drawn_free_and_says_why() -> None:
    scene = ops.set_river(_room(), "stream", mouth="auto")
    moved = copy.deepcopy(scene)
    ops.entities(moved)[0]["x"] = 300.0  # (a pond moved since: the join no longer holds)
    joined, problems = river.mouths(_rivers(moved), river.ponds_of(moved["entities"]))
    assert joined == {} and "isn't in one" in problems["stream"]
    assert _index(moved).level_at(1100.0 / P, 600.0 / P) is not None, "drawn whole, as a free end"
    assert ops.rivers(moved) == ops.rivers(scene), "never reshaped"


# --- independent review round 1 (51fb208) ----------------------------------------------------------------------


def _flat(points: list[list[float]]) -> dict[str, Any]:
    scene = {"entities": [], "settings": {"world_width": 1600, "world_height": 1200,
                                          "hd2d": {"ground": {"texture": "assets/textures/grass.png",
                                                              "from": [0, 0], "to": [1600, 1200]}}}}
    return ops.add_river(scene, "stream", points)


def test_carving_a_river_twice_is_carving_once_even_at_the_ground_s_level() -> None:
    """Measured beside it every quarter metre, its own fresh bed under the corners read there sank it again."""
    for cell in (16, 32):
        for level in (8.0, 0.0, -4.0):
            scene = _flat([[4.0, 600.0, 96.0, level], [700.0, 640.0, 96.0, level], [1596.0, 600.0, 96.0, level]])
            scene["settings"]["hd2d"]["ground"]["cell"] = cell
            once = ops.carve_river_bed(scene, "stream", depths=[0.6, 0.6, 0.6])
            with pytest.raises(ops.OpError, match="already carved"):
                ops.carve_river_bed(once, "stream", depths=[0.6, 0.6, 0.6])
    a = [[4.0, 600.0, 96.0, -16.0], [1596.0, 600.0, 96.0, -16.0]]
    b = [[4.0, 724.0, 96.0, 8.0], [1596.0, 724.0, 96.0, 8.0]]  # 0.88 m from it, bank to bank, over the ground
    scene = ops.carve_river_bed(ops.add_river(_flat(a), "b", b), "b", depths=[0.6, 0.6])
    scene = ops.carve_river_bed(scene, "stream", depths=[0.6, 0.6])
    with pytest.raises(ops.OpError, match="already carved"):
        ops.carve_river_bed(scene, "b", depths=[0.6, 0.6])


def test_its_channel_in_the_pond_stays_water_deep_water_stops_characters_there() -> None:
    """With a mouth the carved bed ran on into the pond as dry ground: walked and navigated 0.7 m down."""
    scene = ops.carve_river_bed(_room(mouth="auto"), "stream")  # (a quarter of its width: 0.75 m)
    world = World(parse_hd2d(scene["settings"]["hd2d"]), {}, river.ponds_of(scene["entities"]))
    x, y = 1050.0 / P, 600.0 / P  # in the pond, over the channel
    bed = min(h for h, _s in world.heights_at(x, y))
    assert bed < -0.6 and world.stand(x, y, bed, 0.3, 0.19) is None, "deep: can't stand there"
    assert world.water_at(x, y, bed) is None, "the pond ripples itself there (no wading step twice)"
    assert world.path((1300.0 / P, 700.0 / P, 0.0), (x, y, bed)) == [], "no way down into it"


def test_review_refusals_classic_ponds_banks_in_the_pond_a_drop_by_the_shore_and_flagged_ponds() -> None:
    scene = _room()
    pond = ops.entities(scene)[0]["id"]
    classic = ops.set_water(scene, pond, preset="pond")
    with pytest.raises(ops.OpError, match="older simple look"):
        ops.set_river(classic, "stream", mouth="auto")
    drop = [[1200.0, 40.0, 96.0, 12.8], [1200.0, 380.0, 96.0, 12.8], [1200.0, 420.0, 96.0, 0.0],
            [1200.0, 600.0, 96.0, 0.0]]  # 0.4 m down over the metre and a half before the shore (the surface eases)
    with pytest.raises(ops.OpError, match=r"0\.36 m above .*over its last 1\.5 m.*points 2 to 4"):
        ops.set_river(scene, "stream", points=drop, mouth="auto")
    flagged = copy.deepcopy(scene)
    ops.find_entity(flagged, pond)["require_flags"] = ["rained"]
    with pytest.raises(ops.OpError, match="shows only when flags say"):
        ops.set_river(flagged, "stream", mouth="auto")
    lake = {"entities": [], "settings": copy.deepcopy(scene["settings"])}
    lake["settings"]["hd2d"].pop("rivers")
    lake, big = ops.place_blank(lake, "start", "Lake", 800.0, 600.0)
    lake = ops.set_water(lake, big, preset="natural_pond", shape="ellipse", width=896.0, height=576.0)
    along = [[300.0, 295.0, 64.0, 0.0], [800.0, 295.0, 64.0, 0.0], [1050.0, 320.0, 64.0, 0.0],
             [1200.0, 420.0, 64.0, 0.0], [1180.0, 600.0, 64.0, 0.0]]  # its south bank in the lake for ~10 m
    with pytest.raises(ops.OpError, match="runs with a bank in the pond"):
        ops.add_river(lake, "stream", along, mouth="auto")
    # the level refusal names the points to change, and doing so is accepted
    low = _room(level=-8.0)
    with pytest.raises(ops.OpError, match="points 2 to 3"):
        ops.set_river(low, "stream", mouth="auto")
    lowered = [list(p) for p in STREAM]
    lowered[1][3] = lowered[2][3] = -8.0
    assert ops.rivers(ops.set_river(low, "stream", points=lowered, mouth="auto"))[0]["mouth"] == "auto"


def test_ponds_are_read_as_their_behaviour_reads_them() -> None:
    scene = _room()
    entity = ops.entities(scene)[0]
    odd = copy.deepcopy(scene)
    ops.entities(odd)[0]["behaviour_config"]["WaterSurface"]["note"] = "a stray key"
    assert [p.id for p in river.ponds_of(odd["entities"])] == [entity["id"]], "unknown keys left aside"
    broken = copy.deepcopy(scene)
    ops.entities(broken)[0]["behaviour_config"] = ["not", "a", "dict"]
    assert river.ponds_of(broken["entities"]) == (), "unreadable: left out, no crash"
