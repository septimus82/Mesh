"""#461 R1: rivers, headless: ``settings.hd2d.rivers`` parsed and checked (sound banks, falling level, no river
meeting another), stored deterministically, and the checked edits Studio and AI make (add_river, set_river,
remove_river). The drawing is tests/test_river_gpu.py."""

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
from engine.hd2d.settings import Hd2dSettingsError, parse_hd2d

pytestmark = pytest.mark.fast

P = 32.0


def _r(points: list[tuple[float, float, float, float]], rid: str = "brook", **look: Any) -> dict[str, Any]:
    """A river from points in metres (x, y, width, level)."""
    return {"id": rid, "points": [[x * P, y * P, w * P, lv * P] for x, y, w, lv in points], **look}


GENTLE_S = _r([(2, 10, 3, 0), (14, 6, 3, -0.1), (26, 12, 3.5, -0.2), (38, 8, 4, -0.3)])
LAKESIDE = _r([(23.75, 29.06, 2.25, 0), (26.88, 27.5, 2.25, 0), (30.0, 26.25, 2.0, -0.3), (32.5, 26.41, 2.0, -0.6),
               (34.38, 26.56, 2.25, -0.8), (36.25, 27.19, 2.75, -0.85), (38.44, 28.28, 3.5, -0.9)])
HAIRPIN_NARROW = _r([(0, 0, 0.8, 0), (8, 0, 0.8, 0), (11, 2.5, 0.8, 0), (8, 5, 0.8, 0), (0, 5, 0.8, 0)])


def _refused(raw: Any) -> str:
    with pytest.raises(river.RiverError) as caught:
        river.parse_rivers(raw)
    return str(caught.value)


def test_a_river_s_ribbon_follows_its_points_and_its_level_only_falls() -> None:
    (parsed,) = river.parse_rivers([GENTLE_S])
    rib = river.ribbon(parsed)
    assert rib.centre[0] == pytest.approx((2, 10)) and rib.centre[-1] == pytest.approx((38, 8)), "through the ends"
    assert all(b - a == pytest.approx(rib.length_m / (len(rib.u) - 1)) for a, b in zip(rib.u, rib.u[1:])), "even steps"
    assert abs(rib.u[1] - river.STEP_M) < 0.01
    assert all(b <= a for a, b in zip(rib.level, rib.level[1:])), "never rises downstream"
    assert rib.half[0] == pytest.approx(1.5) and rib.half[-1] == pytest.approx(2.0), "width interpolated, no overshoot"
    assert min(rib.half) >= 1.5 - 1e-9 and max(rib.half) <= 2.0 + 1e-9
    for k in (0, len(rib.u) // 2, len(rib.u) - 1):  # the banks: half the width either side, left of the flow on the left
        (cx, cy), (tx, ty) = rib.centre[k], rib.tangent[k]
        assert math.dist(rib.left[k], rib.centre[k]) == pytest.approx(rib.half[k])
        assert (rib.left[k][0] - cx) * ty - (rib.left[k][1] - cy) * tx < 0 < (rib.right[k][0] - cx) * ty - (rib.right[k][1] - cy) * tx
    for raw in (LAKESIDE, HAIRPIN_NARROW):  # a real stream's course; a narrow stream bending back on itself, roomily
        river.parse_rivers([raw])


def test_the_same_river_gives_the_same_geometry_and_the_same_saved_form() -> None:
    a = river.parse_rivers([GENTLE_S, _r([(2, 30, 2, 0), (20, 34, 2, -0.5)], "second", flow=0.0)])
    b = river.parse_rivers(json.loads(json.dumps([GENTLE_S, _r([(2, 30, 2, 0), (20, 34, 2, -0.5)], "second",
                                                                flow=0.0)])))
    assert a == b
    (va, ia), (vb, ib) = river.vertices(a, 0.035), river.vertices(b, 0.035)
    assert va.tobytes() == vb.tobytes() and ia.tobytes() == ib.tobytes()
    n = sum(len(river.ribbon(r).u) for r in a)
    assert len(va) == 2 * n * river.FLOATS_PER_VERTEX and len(ia) == 6 * (n - len(a))
    stored = [river.to_json(r) for r in a]
    assert stored[0] == {"id": "brook", "points": GENTLE_S["points"]}, "a plain river stores no look fields"
    assert stored[1]["flow"] == 0.0
    assert [river.to_json(r) for r in river.parse_rivers(stored)] == stored, "saved, reopened, saved: the same"


@pytest.mark.parametrize(("raw", "words"), [
    (_r([(5, 5, 3, 0), (10, 5, 3, 0), (10.6, 6, 3, 0), (5, 7, 3, 0)]), "inner bank folds"),  # wide hairpin
    (_r([(2, 2, 1.5, 0), (10, 2, 1.5, 0), (10, 8, 1.5, 0), (4, 8, 1.5, 0), (6, 0, 1.5, 0)]), "inner bank folds"),
    (_r([(3 * math.cos(a), 3 * math.sin(a), 1.0, 0) for a in [i * 0.75 for i in range(11)]]), "cross or touch"),
    (_r([(0, 0, 1, 0), (10, 0, 1, 0), (12, 2, 1, 0), (10, 4, 1, 0), (4, 1.2, 1, 0), (0, 1.2, 1, 0)]), "cross or touch"),
    (_r([(0, 0, 2, 0), (5, 0, 2, 0.5)]), "would run uphill between points 1 and 2 (its level rises 0.50 m)"),
    (_r([(0, 0, 2, 0), (0.1, 0, 2, 0)]), "closer than a quarter metre"),
])
def test_unsound_rivers_are_refused_saying_why_and_where(raw: dict[str, Any], words: str) -> None:
    message = _refused([raw])
    assert "brook" in message and words in message, message


def test_the_banks_check_refuses_near_touching_but_not_a_roomy_bend() -> None:
    # two arms of a U: 2 m apart is room enough; 1.2 m apart leaves 0.2 m between the banks (under CLEARANCE_M)
    river.parse_rivers([_r([(0, 0, 1, 0), (10, 0, 1, 0), (12, 2, 1, 0), (10, 4, 1, 0), (4, 2, 1, 0), (0, 2, 1, 0)])])
    assert "cross or touch" in _refused([_r([(0, 0, 1, 0), (10, 0, 1, 0), (12, 2, 1, 0), (10, 4, 1, 0), (4, 1.2, 1, 0),
                                             (0, 1.2, 1, 0)])])


def test_rivers_that_meet_or_repeat_an_id_or_say_something_odd_are_refused() -> None:
    crossing = [_r([(0, 0, 2, 0), (20, 0, 2, 0)], "a"), _r([(10, -5, 2, 0), (10, 5, 2, 0)], "b")]
    assert "Rivers 'a' and 'b' cross or overlap" in _refused(crossing)
    inside = [_r([(0, 0, 8, 0), (20, 0, 8, 0)], "wide"), _r([(8, 0, 1, 0), (12, 0, 1, 0)], "within")]
    assert "cross or overlap" in _refused(inside), "one lying wholly on another"
    assert "used twice" in _refused([GENTLE_S, GENTLE_S])
    assert "unknown keys: speed" in _refused([{**GENTLE_S, "speed": 2}])
    assert ".points must be a list of 2 to 64" in _refused([_r([(0, 0, 2, 0)])])
    assert "width must be a number from 16 to 512" in _refused([_r([(0, 0, 0.1, 0), (5, 0, 2, 0)])])
    assert ".flow must be a number from 0 to 8" in _refused([{**GENTLE_S, "flow": 9}])
    assert ".colour" in _refused([{**GENTLE_S, "colour": "blue"}])
    assert "rain_ripples must be true or false" in _refused([{**GENTLE_S, "rain_ripples": 1}])
    assert ".id must be a short name" in _refused([{**GENTLE_S, "id": "Big River"}])
    assert "must be a list" in _refused({"brook": GENTLE_S})


def test_the_room_s_settings_take_rivers_strictly_or_set_broken_ones_aside() -> None:
    assert parse_hd2d({}).rivers == () and parse_hd2d({}).rivers_error is None, "older rooms: none"
    good = parse_hd2d({"rivers": [GENTLE_S]})
    assert [r.id for r in good.rivers] == ["brook"]
    broken = {"rivers": [_r([(0, 0, 2, 0), (5, 0, 2, 0.5)])]}
    with pytest.raises(Hd2dSettingsError, match="uphill"):
        parse_hd2d(broken)
    lenient = parse_hd2d(broken, lenient=True)
    assert lenient.rivers == () and "uphill" in (lenient.rivers_error or ""), "none drawn, the reason kept"


def _hd2d_scene() -> dict[str, Any]:
    return {"entities": [], "settings": {"world_width": 1600, "world_height": 1200,
                                         "hd2d": {"ground": {"texture": "assets/textures/grass.png",
                                                             "from": [0, 0], "to": [1600, 1200]}}}}


def test_the_river_ops_check_everything_before_writing_and_store_it_plainly() -> None:
    scene = _hd2d_scene()
    before = copy.deepcopy(scene)
    out = ops.add_river(scene, "brook", GENTLE_S["points"], flow=1.5, waves=0.25)
    assert scene == before, "the edit is a copy"
    assert ops.rivers(out) == [{"id": "brook", "points": GENTLE_S["points"], "flow": 1.5, "waves": 0.25}]
    with pytest.raises(ops.OpError, match="uphill"):
        ops.set_river(out, "brook", points=[[0, 0, 64, 0], [160, 0, 64, 16]])
    with pytest.raises(ops.OpError, match="inner bank folds"):
        ops.add_river(out, "hairpin", [[160, 160, 96, 0], [320, 160, 96, 0], [339, 192, 96, 0], [160, 224, 96, 0]])
    with pytest.raises(ops.OpError, match="cross or overlap"):
        ops.add_river(out, "across", [[400, 0, 64, 0], [400, 600, 64, 0]])
    with pytest.raises(ops.OpError, match="already has a river 'brook'"):
        ops.add_river(out, "brook", [[0, 900, 64, 0], [300, 900, 64, 0]])
    with pytest.raises(ops.OpError, match="no river 'creek'"):
        ops.set_river(out, "creek", flow=0)
    with pytest.raises(ops.OpError, match="no river 'creek'"):
        ops.remove_river(out, "creek")
    assert ops.rivers(out) == [{"id": "brook", "points": GENTLE_S["points"], "flow": 1.5, "waves": 0.25}], "unchanged"
    still = ops.set_river(out, "brook", flow=0, colour="#336677")
    assert ops.rivers(still)[0]["flow"] == 0.0 and ops.rivers(still)[0]["colour"] == "#336677"
    assert ops.rivers(ops.set_river(still, "brook", flow=1.0, waves=0.5))[0] == {
        "id": "brook", "points": GENTLE_S["points"], "colour": "#336677"}, "back to a default: the field dropped"
    gone = ops.remove_river(still, "brook")
    assert "rivers" not in gone["settings"]["hd2d"], "the last one removed: no key, as older rooms"
    with pytest.raises(ops.OpError, match="isn't HD-2D"):
        ops.add_river({"entities": [], "settings": {}}, "brook", GENTLE_S["points"])


def test_ai_adds_reviews_and_saves_a_river(tmp_path: Path) -> None:
    from engine.project_scaffold import create_project
    from engine.studio_project import Project

    assert {"add_river", "set_river", "remove_river"} <= set(authoring.operations())
    root = tmp_path / "game"
    create_project(root, "Game", template_id="hd2d_rpg")
    project = Project(root, json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"])
    room = project.current
    before = project.scene(room)
    points = [[100, 100, 64, -4], [300, 80, 64, -6], [500, 110, 72, -8]]
    authoring.apply(project, [{"op": "add_river", "room": room, "river_id": "brook", "points": points, "flow": 0.8}])
    after = project.scene(room)
    project.save()
    lines = authoring.summarize({"rooms": {room: before}}, {"rooms": {room: after}})
    assert any("adds river 'brook' (3 points, flowing 0.8 m/s)" in line for line in lines), lines
    changed = ops.set_river(after, "brook", flow=0)
    assert any("changes river 'brook' (flow)" in line for line in authoring.summarize(
        {"rooms": {room: after}}, {"rooms": {room: changed}})), "the AI review names the change"
    assert any("removes river 'brook'" in line for line in authoring.summarize(
        {"rooms": {room: after}}, {"rooms": {room: ops.remove_river(after, "brook")}}))
    # saved: reopened from disk, the same river
    reopened = Project(root, json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"])
    raw = reopened.scene(room)["settings"]["hd2d"]
    assert raw["rivers"] == [{"id": "brook", "points": [[float(v) for v in p] for p in points], "flow": 0.8}]
    assert [r.id for r in parse_hd2d(raw).rivers] == ["brook"]


def test_a_river_stays_on_its_room_s_ground_strictly_leniently_and_through_the_ops() -> None:
    ground = {"ground": {"texture": "assets/textures/grass.png", "from": [0, 0], "to": [1600, 1200]}}
    edge = [[0, 32, 64, 0], [400, 32, 64, 0]]  # its right bank exactly on the ground's south edge (y 0)
    off = [[0, 20, 64, 0], [400, 20, 64, 0]]  # 12 px off it
    assert [r.id for r in parse_hd2d({**ground, "rivers": [{"id": "edge", "points": edge}]}).rivers] == ["edge"]
    with pytest.raises(Hd2dSettingsError, match=r"River 'off' reaches off the room's ground near \(\d+, -12\) px"):
        parse_hd2d({**ground, "rivers": [{"id": "off", "points": off}]})
    lenient = parse_hd2d({**ground, "rivers": [{"id": "off", "points": off}]}, lenient=True)
    assert lenient.rivers == () and "reaches off the room's ground" in (lenient.rivers_error or "")
    # no ground block: the room's map is its extent
    assert "reaches off" in (parse_hd2d({"rivers": [{"id": "off", "points": off}]}, map_size_px=(1600, 1200),
                                        lenient=True).rivers_error or "")
    scene = _hd2d_scene()
    with pytest.raises(ops.OpError, match="reaches off the room's ground"):
        ops.add_river(scene, "off", off)
    with pytest.raises(ops.OpError, match="reaches off the room's ground"):
        ops.add_river(scene, "far", [[5000, 5000, 64, 0], [5400, 5000, 64, 0]])  # wholly elsewhere
    saved = ops.add_river(scene, "edge", [[0.004, 32.004, 64, 0], [400, 32.004, 64, 0]])  # stored rounded
    reopened = json.loads(json.dumps(saved))
    assert [r.id for r in parse_hd2d(reopened["settings"]["hd2d"]).rivers] == ["edge"], "saved, reopened: still on it"


def _long(rid: str, y: float, metres: float) -> dict[str, Any]:
    """A straight river ``metres`` long, east along y (m)."""
    return _r([(1, y, 2, 0), (1 + metres, y, 2, 0)], rid)


def test_a_room_s_rivers_have_a_bounded_cost_checked_before_they_are_sampled() -> None:
    assert river.MAX_LENGTH_M == 1024 and river.MAX_TOTAL_M == 2048 and river.MAX_RIVERS == 16
    river.parse_rivers([_long("long", 4, 1000)])  # a kilometre: allowed
    assert "is 1100 m long: a river may be at most 1024 m" in _refused([_long("long", 4, 1100)])
    assert "rivers are 2100 m long together: at most 2048 m" in _refused(
        [_long("a", 4, 700), _long("b", 12, 700), _long("c", 20, 700)])
    assert "at most 16 rivers (got 17)" in _refused([_long(f"r{i}", 4 + 8 * i, 10) for i in range(17)])
    big = {"ground": {"texture": "assets/textures/grass.png", "from": [0, 0], "to": [65536, 4096]}}
    with pytest.raises(Hd2dSettingsError, match="at most 1024 m"):
        parse_hd2d({**big, "rivers": [_long("long", 4, 1100)]})
    lenient = parse_hd2d({**big, "rivers": [_long("long", 4, 1100)]}, lenient=True)
    assert lenient.rivers == () and "at most 1024 m" in (lenient.rivers_error or "")
    # a zigzag of 64 points, each span the room's diagonal: refused from its course's length alone, quickly
    import time

    zigzag = {"id": "zig", "points": [[0 if i % 2 else 8000, 8000 * (i % 3 == 1), 64, 0] for i in range(64)]}
    start = time.perf_counter()
    assert "a river may be at most 1024 m" in _refused([zigzag])
    assert time.perf_counter() - start < 1.0, "no ribbon sampled for it"


def test_the_water_s_clock_runs_for_a_room_with_rivers_and_no_ponds() -> None:
    from types import SimpleNamespace

    from engine import water

    (brook,) = river.parse_rivers([GENTLE_S])
    with_river = SimpleNamespace(water_bodies=[], water_time=0.0,
                                 hd2d_renderer=SimpleNamespace(settings=SimpleNamespace(rivers=(brook,))))
    water.advance(with_river, 0.25)
    assert with_river.water_time == 0.25
    dry = SimpleNamespace(water_bodies=[], water_time=0.0, hd2d_renderer=SimpleNamespace(settings=SimpleNamespace(rivers=())))
    water.advance(dry, 0.25)
    assert dry.water_time == 0.0, "no water: the clock stays"
    flat_2d = SimpleNamespace(water_bodies=["pond"], water_time=0.0, hd2d_renderer=None)
    water.advance(flat_2d, 0.25)
    assert flat_2d.water_time == 0.25, "a 2D room's ponds as before"
