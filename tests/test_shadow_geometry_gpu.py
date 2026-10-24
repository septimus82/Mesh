"""Milestone 12: shadow shapes, checked pixel by pixel against where the light can actually reach.

For each scene (corners, a diagonal wall, a short block, a wall running past the light's reach, a lamp
right against a wall or a corner, a lamp moving past a pillar) every floor point on a grid is classed
by a ray test: the lamp sees it, or a wall is in the way. A lit point must look exactly like the room
with shadows off; a blocked point exactly like the room light alone. Points within a few pixels of a
shadow's edge, inside a wall, or at the rim of the light are left out (pixel rounding, not geometry).
No beams beyond the light, no gaps between joined walls, no shadow over the lamp's side, no lit wedges.

GL-gated: set MESH_GL_SMOKE=1 (with a display and a GPU).
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

Point = tuple[float, float]


def _rect_poly(x: float, y: float, w: float, h: float) -> list[Point]:
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


def _cross(o: Point, a: Point, b: Point) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _segments_cross(p: Point, q: Point, a: Point, b: Point) -> bool:
    d1, d2 = _cross(a, b, p), _cross(a, b, q)
    d3, d4 = _cross(p, q, a), _cross(p, q, b)
    return (d1 > 0) != (d2 > 0) and (d3 > 0) != (d4 > 0)


def _inside(pt: Point, poly: list[Point]) -> bool:
    inside = False
    for (x0, y0), (x1, y1) in zip(poly, [*poly[1:], poly[0]]):
        if (y0 > pt[1]) != (y1 > pt[1]) and pt[0] < x0 + (pt[1] - y0) * (x1 - x0) / (y1 - y0):
            inside = not inside
    return inside


def _dist_to_segment(p: Point, a: Point, b: Point) -> float:
    ax, ay, bx, by = a[0], a[1], b[0], b[1]
    t = max(0.0, min(1.0, ((p[0] - ax) * (bx - ax) + (p[1] - ay) * (by - ay)) / max(1e-9, (bx - ax) ** 2 + (by - ay) ** 2)))
    return math.hypot(p[0] - (ax + t * (bx - ax)), p[1] - (ay + t * (by - ay)))


def _blocked(light: Point, pt: Point, shapes: list[list[Point]]) -> bool:
    return any(_segments_cross(light, pt, a, b) for poly in shapes for a, b in zip(poly, [*poly[1:], poly[0]]))


def _near_edge_of_shadow(light: Point, pt: Point, shapes: list[list[Point]], margin: float) -> bool:
    """Within ``margin`` px of a shadow boundary: a ray from the light through a corner, or a wall."""
    for poly in shapes:
        for a, b in zip(poly, [*poly[1:], poly[0]]):
            if _dist_to_segment(pt, a, b) < margin:
                return True
        for c in poly:
            dx, dy = c[0] - light[0], c[1] - light[1]
            d = math.hypot(dx, dy)
            if d < 1e-6:
                continue
            far = (light[0] + dx / d * 4000, light[1] + dy / d * 4000)
            if _dist_to_segment(pt, c, far) < margin:
                return True
    return False


SCENES = {
    # name: (light, radius, rect walls, polygon walls)
    "l_corner": ((200.0, 200.0), 220.0, [(280.0, 120.0, 24.0, 180.0), (280.0, 276.0, 160.0, 24.0)], []),
    "diagonal_wall": ((180.0, 240.0), 230.0, [], [[(300.0, 140.0), (320.0, 140.0), (420.0, 330.0), (400.0, 330.0)]]),
    "short_block": ((220.0, 220.0), 200.0, [(300.0, 210.0, 16.0, 16.0)], []),
    "wall_past_the_reach": ((240.0, 240.0), 160.0, [(330.0, 20.0, 24.0, 440.0)], []),
    "lamp_against_a_wall": ((290.0, 240.0), 200.0, [(300.0, 140.0, 24.0, 200.0)], []),
    "lamp_by_a_corner": ((292.0, 352.0), 200.0, [(300.0, 140.0, 24.0, 200.0), (300.0, 340.0, 140.0, 24.0)], []),
    "joined_wall_tiles": ((200.0, 120.0), 260.0, [(300.0 + 32 * i, 200.0, 32.0, 32.0) for i in range(5)], []),
    "pentagon_pillar": ((200.0, 240.0), 220.0, [], [[(330.0, 200.0), (370.0, 210.0), (380.0, 250.0), (345.0, 280.0), (315.0, 245.0)]]),
    # A lamp right beside a long slanted wall: its far edge spans a wide angle (a straight shadow end left a lit wedge).
    "lamp_by_a_long_slanted_wall": ((300.0, 240.0), 200.0, [], [[(320.0, 60.0), (340.0, 60.0), (360.0, 430.0), (340.0, 430.0)]]),
}
MOVING = [((140.0 + 30 * i, 120.0 + 18 * i), 220.0, [(300.0, 200.0, 40.0, 40.0)], []) for i in range(6)]


@pytest.fixture(scope="module")
def bench():
    from shadow_bench import Bench

    os.environ.pop("MESH_SHADOWS_RENDERER", None)
    b = Bench()
    yield b
    b.close()


def _mismatches(bench, light: Point, radius: float, rects: list, polys: list) -> tuple[int, int, list]:
    from shadow_bench import Scene, light as lamp

    walls = [tuple(r) for r in rects]
    shapes = [_rect_poly(*r) for r in rects] + [list(p) for p in polys]
    bench.load(Scene(lights=[lamp(*light, radius)], walls=walls, polys=polys))
    lit = bench.frame()
    bench.load(Scene(lights=[lamp(*light, radius)], walls=walls, polys=polys, shadows="none"))
    unshadowed = bench.frame()
    bench.load(Scene(lights=[], walls=walls, polys=polys))
    room_only = bench.frame()
    checked, wrong = 0, []
    for gx in range(4, 640, 10):
        for gy in range(4, 480, 10):
            pt = (float(gx), float(gy))
            d = math.hypot(pt[0] - light[0], pt[1] - light[1])
            if d < 6 or d > radius * 0.97 or any(_inside(pt, s) for s in shapes):
                continue
            if _near_edge_of_shadow(light, pt, shapes, 3.0):
                continue
            expect = room_only if _blocked(light, pt, shapes) else unshadowed
            got, want = bench.pixel(lit, pt), bench.pixel(expect, pt)
            checked += 1
            if any(abs(a - b) > 2 for a, b in zip(got, want)):
                wrong.append((pt, "blocked" if expect is room_only else "lit", got, want))
    return checked, len(wrong), wrong[:6]


@pytest.mark.parametrize("name", list(SCENES))
def test_every_shadow_falls_exactly_where_the_lamp_cannot_reach(bench, name: str) -> None:
    light, radius, rects, polys = SCENES[name]
    checked, wrong, examples = _mismatches(bench, light, radius, rects, polys)
    assert checked > 150, f"{name}: too few points checked ({checked})"
    assert wrong == 0, f"{name}: {wrong} of {checked} points wrong, e.g. {examples}"


def test_a_lamp_moving_past_a_pillar_keeps_a_correct_shadow_at_every_step(bench) -> None:
    for light, radius, rects, polys in MOVING:
        checked, wrong, examples = _mismatches(bench, light, radius, rects, polys)
        assert wrong == 0, f"lamp at {light}: {wrong} of {checked} wrong, e.g. {examples}"
