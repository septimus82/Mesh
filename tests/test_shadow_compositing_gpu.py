"""Milestone 12: a shadow blocks only the light that casts it; the room light stays (real GPU pixels).

The scenes are tooling/shadow_bench.py's: a flat grey floor, a wall, point lights and a room light,
drawn through the engine's LightManager on a small real Arcade window and read back as pixels.
Before Milestone 12 a shadow was black painted over the finished picture: behind the wall the floor was
darker than the room light alone, and a second lamp's light there was painted out too.

GL-gated like the other real-render tests: set MESH_GL_SMOKE=1 (with a display and a GPU).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from engine import optional_arcade

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1" or not optional_arcade.has_arcade(),
                       reason="real-GPU render test is opt-in (set MESH_GL_SMOKE=1 with a display/GL context)"),
]

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tooling"))

WALL = (300.0, 140.0, 24.0, 200.0)
BEHIND, LIT, FAR = (380, 240), (240, 240), (600, 40)  # behind the wall from the lamp, near the lamp, out of reach


def _close(a: tuple[int, ...], b: tuple[int, ...], tolerance: int = 2) -> bool:
    return all(abs(x - y) <= tolerance for x, y in zip(a, b))


@pytest.fixture(scope="module")
def bench():
    from shadow_bench import Bench

    os.environ.pop("MESH_SHADOWS_RENDERER", None)
    b = Bench()
    yield b
    b.close()


def _shot(bench, **scene):
    from shadow_bench import Scene

    bench.load(Scene(**scene))
    return bench.frame()


def _lamp(x: float, y: float, colour: str = "#ffffff", radius: float = 200, **extra):
    from shadow_bench import light

    return light(x, y, radius, colour, **extra)


def test_a_wall_blocks_its_lamp_and_the_room_light_stays(bench) -> None:
    shadowed = _shot(bench, lights=[_lamp(200, 240)], walls=[WALL])
    room_only = _shot(bench, lights=[], walls=[WALL])
    behind = bench.pixel(shadowed, BEHIND)
    assert _close(behind, bench.pixel(room_only, BEHIND)), f"behind the wall: {behind}, room light alone: {bench.pixel(room_only, BEHIND)}"
    assert bench.pixel(shadowed, LIT)[0] > behind[0] + 60, "the lamp's own side should be lit"


def test_one_lamps_shadow_does_not_darken_another_lamp(bench) -> None:
    both = _shot(bench, lights=[_lamp(200, 240), _lamp(420, 420, "#88bbff")], walls=[WALL])
    b_alone = _shot(bench, lights=[_lamp(420, 420, "#88bbff")], walls=[WALL])
    assert _close(bench.pixel(both, BEHIND), bench.pixel(b_alone, BEHIND)), (bench.pixel(both, BEHIND), bench.pixel(b_alone, BEHIND))


def test_a_lamps_shadow_never_falls_below_the_room_light(bench) -> None:
    """Lamp B's shadow lies over the far side of the wall: only B's light goes, the room light stays."""
    b_alone = _shot(bench, lights=[_lamp(420, 420, "#88bbff")], walls=[WALL])
    room_only = _shot(bench, lights=[], walls=[WALL])
    assert _close(bench.pixel(b_alone, LIT), bench.pixel(room_only, LIT))


def test_shadows_on_with_no_lamps_changes_nothing(bench) -> None:
    on = _shot(bench, lights=[], walls=[WALL], shadows="hard")
    off = _shot(bench, lights=[], walls=[WALL], shadows="none")
    assert list(on.getdata()) == list(off.getdata())


def test_daylight_stays_in_a_lamps_shadow(bench) -> None:
    day = (200, 200, 190)
    lamp = _shot(bench, ambient=day, lights=[_lamp(200, 240)], walls=[WALL])
    no_lamp = _shot(bench, ambient=day, lights=[], walls=[WALL])
    assert _close(bench.pixel(lamp, BEHIND), bench.pixel(no_lamp, BEHIND))


def test_with_nothing_to_block_shadows_look_exactly_as_lighting_without_them(bench) -> None:
    lights = [_lamp(200, 240), _lamp(420, 420, "#ff5555")]
    on = _shot(bench, lights=lights, shadows="hard")
    off = _shot(bench, lights=lights, shadows="none")
    assert list(on.getdata()) == list(off.getdata())


def test_a_lamp_set_not_to_cast_shadows_shines_through(bench) -> None:
    open_floor = _shot(bench, lights=[_lamp(200, 240, shadows=False)], walls=[WALL], shadows="none")
    no_shadow = _shot(bench, lights=[_lamp(200, 240, shadows=False)], walls=[WALL])
    assert _close(bench.pixel(no_shadow, BEHIND), bench.pixel(open_floor, BEHIND))


def test_beyond_the_shadow_budget_lamps_light_without_shadows_and_say_so(bench) -> None:
    from shadow_bench import Scene

    bench.manager.shadow_light_budget = 1
    try:
        bench.load(Scene(lights=[_lamp(200, 240), _lamp(420, 240)], walls=[WALL]))
        image = bench.frame()
        stats = dict(bench.manager._last_lighting_stats)
    finally:
        bench.manager.shadow_light_budget = 16
    assert stats["shadowed_lights"] == 1 and stats["lights_over_budget"] == 1, stats
    room_only = _shot(bench, lights=[], walls=[WALL])
    assert bench.pixel(image, (330, 240))[0] > bench.pixel(room_only, (330, 240))[0], "no black: the extra lamp still lights"


def test_shadows_stay_on_their_wall_when_the_camera_scrolls_and_zooms(bench) -> None:
    for camera, zoom in (((100.0, 60.0), 1.0), ((180.0, 120.0), 2.0), ((-50.0, -40.0), 0.75)):
        lamp = _shot(bench, lights=[_lamp(200, 240)], walls=[WALL], camera=camera, zoom=zoom)
        room = _shot(bench, lights=[], walls=[WALL], camera=camera, zoom=zoom)
        assert _close(bench.pixel(lamp, BEHIND), bench.pixel(room, BEHIND)), (camera, zoom)
        assert bench.pixel(lamp, (230, 240))[0] > bench.pixel(room, (230, 240))[0] + 40, (camera, zoom)


def test_when_the_gpu_cannot_build_the_shadow_renderer_the_room_is_lit_without_shadows(bench) -> None:
    from shadow_bench import Scene

    scene = Scene(lights=[_lamp(200, 240)], walls=[WALL])
    unshadowed = _shot(bench, lights=[_lamp(200, 240)], walls=[WALL], shadows="none")
    saved = bench.manager._compositor
    bench.manager._compositor = False  # what a failed build leaves
    try:
        bench.load(scene)
        image = bench.frame()
        stats = dict(bench.manager._last_lighting_stats)
    finally:
        bench.manager._compositor = saved
    assert list(image.getdata()) == list(unshadowed.getdata())
    assert stats.get("shadows_unavailable"), stats


def _softly(bench, softness: str, **scene):
    return _shot(bench, settings={"lighting_shadow_softness": softness}, **scene)


@pytest.mark.parametrize("softness", ["soft", "softer"])
def test_a_soft_shadow_still_leaves_the_room_light_in_its_core(bench, softness: str) -> None:
    image = _softly(bench, softness, lights=[_lamp(200, 240)], walls=[WALL])
    room_only = _shot(bench, lights=[], walls=[WALL])
    for point in ((380, 240), (420, 230), (450, 250)):  # deep behind the wall
        assert _close(bench.pixel(image, point), bench.pixel(room_only, point)), (softness, point)


@pytest.mark.parametrize("softness", ["soft", "softer"])
def test_joined_wall_tiles_cast_the_same_soft_shadow_as_one_wall(bench, softness: str) -> None:
    """Each sample of the lamp counts once per pixel, however many tiles' shadows overlap there."""
    tiles = [(300.0 + 32 * i, 200.0, 32.0, 32.0) for i in range(5)]
    joined = _softly(bench, softness, lights=[_lamp(260, 120)], walls=tiles)
    whole = _softly(bench, softness, lights=[_lamp(260, 120)], walls=[(300.0, 200.0, 160.0, 32.0)])
    worst, where = 0, None
    for x in range(0, 640, 2):
        for y in range(0, 480, 2):
            if 298 <= x <= 462 and 198 <= y <= 234:
                continue  # the wall itself: separate tiles shade each other's tops, one wall has no inner edges
            d = max(abs(m - n) for m, n in zip(bench.pixel(joined, (x, y)), bench.pixel(whole, (x, y))))
            if d > worst:
                worst, where = d, (x, y)
    assert worst <= 3, f"{softness}: the joined tiles' shadow differs from one wall's by up to {worst} at {where}"


def test_a_soft_edge_is_narrow_at_the_wall_and_wider_far_from_it(bench) -> None:
    """A penumbra, not a blur: the lamp is a small disc, so the edge widens with distance from the wall."""
    image = _softly(bench, "softer", lights=[_lamp(180, 240, radius=480)], walls=[WALL])
    unshadowed = _shot(bench, lights=[_lamp(180, 240, radius=480)], walls=[WALL], shadows="none")
    room_only = _shot(bench, lights=[], walls=[WALL])

    def width(x: float) -> int:
        """How many pixels, crossing the shadow's upper edge at column x, are part-lit."""
        part = 0
        for y in range(200, 480):
            got, lit, dark = bench.pixel(image, (x, y))[0], bench.pixel(unshadowed, (x, y))[0], bench.pixel(room_only, (x, y))[0]
            if lit - dark > 12 and dark + 3 < got < lit - 3:
                part += 1
        return part

    near, far = width(335.0), width(450.0)
    assert 0 < near < far, f"edge width near the wall {near} px, farther away {far} px"


def test_softness_changes_nothing_for_a_lamp_with_nothing_to_block(bench) -> None:
    sharp = _shot(bench, lights=[_lamp(200, 240)])
    soft = _softly(bench, "softer", lights=[_lamp(200, 240)])
    assert list(sharp.getdata()) == list(soft.getdata())
