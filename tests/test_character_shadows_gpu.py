"""Milestone 12.1: characters cast directional shadows from lamps, through the same per-light masks as walls.

Real GPU pixels (tooling/shadow_bench.py): a flat grey floor, the starter hero, one or two lamps. A
character's shadow starts at its feet, points away from the lamp, takes away only that lamp's light (never
the room light or another lamp's), never darkens the character itself, and goes when the character or the
lamp is set not to cast it. GL-gated: set MESH_GL_SMOKE=1.
"""

from __future__ import annotations

import math
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

LAMP = (200.0, 240.0)
HERO = (300.0, 240.0)  # the sprite's centre; its feet are 24 px lower


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


def _lamp(x: float, y: float, colour: str = "#ffffff", radius: float = 300, **extra):
    from shadow_bench import light

    return light(x, y, radius, colour, **extra)


def _feet(bench) -> tuple[float, float]:
    sprite = bench.sprites[0]
    return float(sprite.center_x), float(sprite.bottom)


def _along(bench, lamp: tuple[float, float], distance: float) -> tuple[float, float]:
    """A floor point ``distance`` px from the feet, straight away from the lamp: inside the shadow."""
    fx, fy = _feet(bench)
    dx, dy = fx - lamp[0], fy - lamp[1]
    d = math.hypot(dx, dy)
    return fx + dx / d * distance, fy + dy / d * distance


def test_a_character_casts_a_shadow_away_from_the_lamp(bench) -> None:
    with_hero = _shot(bench, lights=[_lamp(*LAMP)], characters=[(*HERO, 0, {})])
    behind = _along(bench, LAMP, 30)
    no_shadow = _shot(bench, lights=[_lamp(*LAMP)], characters=[(*HERO, 0, {"cast_shadow": False})])
    room = _shot(bench, lights=[], characters=[(*HERO, 0, {"cast_shadow": False})])
    got, lit, dark = (bench.pixel(img, behind)[0] for img in (with_hero, no_shadow, room))
    assert got < lit - 15, f"behind the character, away from the lamp: {got} (lit {lit})"
    assert got >= dark - 1, f"a character's shadow never goes below the room light: {got} vs {dark}"
    toward = (_feet(bench)[0] - 30, _feet(bench)[1])  # on the lamp's side of the feet
    assert abs(bench.pixel(with_hero, toward)[0] - bench.pixel(no_shadow, toward)[0]) <= 2, "no shadow on the lamp's side"


def test_a_characters_shadow_takes_only_its_own_lamps_light(bench) -> None:
    other = (300.0, 420.0)  # a second lamp above: its shadow falls downward, not where this one falls
    both = _shot(bench, lights=[_lamp(*LAMP), _lamp(*other, "#88bbff")], characters=[(*HERO, 0, {})])
    behind = _along(bench, LAMP, 34)
    only_other = _shot(bench, lights=[_lamp(*other, "#88bbff")], characters=[(*HERO, 0, {})])
    lamp_only_lit = _shot(bench, lights=[_lamp(*LAMP)], characters=[(*HERO, 0, {"cast_shadow": False})])
    room = _shot(bench, lights=[], characters=[(*HERO, 0, {"cast_shadow": False})])
    # Behind the hero from the first lamp: the second lamp's light is all still there.
    a, b = bench.pixel(both, behind), bench.pixel(only_other, behind)
    first_lamp_left = bench.pixel(lamp_only_lit, behind)[2] - bench.pixel(room, behind)[2]
    assert a[2] >= b[2] - 2, f"the other lamp's light survives: {a} vs {b}"
    assert a[2] - b[2] < first_lamp_left, "and the first lamp's light is (mostly) gone there"


def test_the_character_itself_is_not_darkened_by_its_own_shadow(bench) -> None:
    lamp_below = (300.0, 120.0)  # the shadow falls up the screen, over where the body is drawn
    on = _shot(bench, lights=[_lamp(*lamp_below)], characters=[(*HERO, 0, {})])
    off = _shot(bench, lights=[_lamp(*lamp_below)], characters=[(*HERO, 0, {"cast_shadow": False})])
    for dy in (-12, 0, 12):  # across the body
        point = (HERO[0], HERO[1] + dy)
        assert abs(bench.pixel(on, point)[0] - bench.pixel(off, point)[0]) <= 2, point


def test_a_lamp_set_not_to_cast_shadows_casts_no_character_shadow(bench) -> None:
    on = _shot(bench, lights=[_lamp(*LAMP, shadows=False)], characters=[(*HERO, 0, {})])
    off = _shot(bench, lights=[_lamp(*LAMP, shadows=False)], characters=[(*HERO, 0, {"cast_shadow": False})])
    assert list(on.getdata()) == list(off.getdata())


def test_walking_frames_do_not_make_the_shadow_breathe(bench) -> None:
    """The shadow's length comes from the character, not the frame: the tip stays put over a walk cycle."""
    tips = []
    for frame in (8, 9, 10, 11):  # the walk-right row
        image = _shot(bench, lights=[_lamp(*LAMP)], characters=[(*HERO, frame, {})])
        lit = [d for d in range(10, 140) if bench.pixel(image, _along(bench, LAMP, d))[0]
               < bench.pixel(image, (_feet(bench)[0] + d, _feet(bench)[1] + 60))[0] - 10]
        tips.append(max(lit) if lit else 0)
    assert max(tips) - min(tips) <= 6, f"shadow length over the walk frames: {tips}"


def test_shadow_strength_is_how_much_of_the_lamp_it_blocks(bench) -> None:
    behind = None
    values = []
    for strength in (0.3, 0.85):
        image = _shot(bench, lights=[_lamp(*LAMP)], characters=[(*HERO, 0, {"cast_shadow": {"strength": strength}})])
        behind = behind or _along(bench, LAMP, 30)
        values.append(bench.pixel(image, behind)[0])
    assert values[0] > values[1] + 10, values


def test_room_fine_tuning_strength_edge_and_the_character_switch(bench) -> None:
    """Fine-tune shadows: a weaker shadow lets some of the lamp through (never darker), a wider edge
    widens the soft edge, and the room's switch takes characters' shadows away (walls keep theirs)."""
    lamp, wall = [_lamp(*LAMP)], [(240.0, 300.0, 16.0, 60.0)]
    full = _shot(bench, lights=lamp, characters=[(*HERO, 0, {})])
    behind = _along(bench, LAMP, 30)
    half = _shot(bench, lights=lamp, characters=[(*HERO, 0, {})], settings={"lighting_shadow_strength": 0.4})
    lit = _shot(bench, lights=lamp, characters=[(*HERO, 0, {"cast_shadow": False})])
    a, b, c = (bench.pixel(img, behind)[0] for img in (full, half, lit))
    assert a + 8 < b < c, f"strength 0.4 lies between a full shadow and none: {a}, {b}, {c}"
    off = _shot(bench, lights=lamp, walls=wall, characters=[(*HERO, 0, {})], settings={"lighting_character_shadows": False})
    on = _shot(bench, lights=lamp, walls=wall, characters=[(*HERO, 0, {"cast_shadow": False})])
    assert list(off.getdata()) == list(on.getdata()), "the room's switch: no character shadows, the wall's stays"

    def edge_width(settings: dict) -> int:
        image = _shot(bench, lights=lamp, walls=wall, settings=settings)
        row = [bench.pixel(image, (x, 330.0))[0] for x in range(250, 460)]  # across the wall's shadow, sideways
        column = [bench.pixel(image, (300.0, y))[0] for y in range(300, 420)]
        values = row + column
        low, high = min(values), max(values)
        return sum(1 for v in values if low + 0.1 * (high - low) < v < low + 0.9 * (high - low))

    assert edge_width({"lighting_shadow_softness": "soft", "lighting_shadow_edge": 30}) \
        > edge_width({"lighting_shadow_softness": "soft", "lighting_shadow_edge": 6}) + 4


def _separate_dips(values: list[int], prominence: float = 4.0) -> int:
    """Dark dips with a lighter gap on both sides: separate copies of the silhouette (streaks), not one shadow."""
    count = 0
    for i in range(1, len(values) - 1):
        if values[i] < values[i - 1] and values[i] <= values[i + 1]:
            if min(max(values[max(0, i - 6):i]), max(values[i + 1:i + 7])) - values[i] >= prominence:
                count += 1
    return count


def test_a_soft_character_shadow_is_one_shadow_not_streaks(bench) -> None:
    """Milestone 14: at Softer the lamp's 16 sample points spread a thin silhouette into separate copies. Across the
    shadow there must be one smooth dark band (before: 1-2 extra dips 50-70 px from the feet)."""
    for softness in ("soft", "softer"):
        image = _shot(bench, lights=[_lamp(*LAMP)], characters=[(*HERO, 0, {})],
                      settings={"lighting_shadow_softness": softness})
        fx, fy = _feet(bench)
        for d in (30, 50, 70):
            column = [bench.pixel(image, (fx + d, fy + dy))[0] for dy in range(-40, 41)]
            assert _separate_dips(column) == 0, (softness, d, column)
