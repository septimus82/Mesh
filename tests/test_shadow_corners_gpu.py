"""Milestone 12.2: corners and joints at every edge style, checked pixel by pixel (hidden window, no input).

Each pixel is compared with what the renderer means to draw: the room light plus each lamp's light times the share
of the lamp's sample points that see the pixel (a point lamp at Sharp; 12 or 16 points at Soft and Softer, less any
inside a wall). Before 12.2 a Softer lamp beside a corner leaked wedges of light behind both walls (about half of
that scene's pixels wrong), and an L of wall tiles shadowed its own face at the joint.

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
sys.path.insert(0, str(Path(__file__).resolve().parent))

L_WALLS = [(280.0, 120.0, 24.0, 180.0), (280.0, 276.0, 160.0, 24.0)]
SCENES = {  # lamps, rectangle walls
    "outside_of_an_l": ([(200.0, 200.0)], L_WALLS),
    "inside_an_l": ([(360.0, 210.0)], L_WALLS),
    "lamp_in_the_corner": ([(318.0, 262.0)], L_WALLS),
    "two_lamps_on_one_joint": ([(200.0, 200.0), (380.0, 380.0)], L_WALLS),
}


@pytest.fixture(scope="module")
def bench():
    from shadow_bench import Bench

    os.environ.pop("MESH_SHADOWS_RENDERER", None)
    b = Bench()
    yield b
    b.close()


def _wrong(bench, lamps, rects, preset: str) -> tuple[int, int]:
    from shadow_bench import Scene, light
    from test_shadow_geometry_gpu import _blocked, _inside, _rect_poly

    from engine.lighting.light_compositor import SOFTNESS, _disc

    size, count = SOFTNESS[preset]
    settings = {"lighting_shadow_softness": preset}
    shapes = [_rect_poly(*r) for r in rects]
    bench.load(Scene(lights=[light(*lp, 260) for lp in lamps], walls=rects, settings=settings))
    shot = bench.frame()
    bench.load(Scene(lights=[], walls=rects, settings=settings))
    room = bench.frame()
    alone = []
    for lp in lamps:
        bench.load(Scene(lights=[light(*lp, 260)], walls=rects, shadows="none", settings=settings))
        alone.append(bench.frame())
    samples = []
    for lp in lamps:
        points = [(lp[0] + dx, lp[1] + dy) for dx, dy in _disc(size, count)]
        clear = [p for p in points if count == 1 or not any(_inside(p, s) for s in shapes)] or [lp]
        samples.append(clear)
    checked = wrong = 0
    for gx in range(4, 640, 8):
        for gy in range(4, 480, 8):
            pt = (float(gx), float(gy))
            if any(_inside(pt, s) for s in shapes) or any(math.hypot(pt[0] - lp[0], pt[1] - lp[1]) < 8 for lp in lamps):
                continue
            want = list(bench.pixel(room, pt))
            for clear, image in zip(samples, alone):
                seen = sum(0 if _blocked(p, pt, shapes) else 1 for p in clear) / len(clear)
                want = [w + (a - r) * seen for w, a, r in zip(want, bench.pixel(image, pt), bench.pixel(room, pt))]
            checked += 1
            wrong += max(abs(g - w) for g, w in zip(bench.pixel(shot, pt), want)) > 6
    return checked, wrong


@pytest.mark.parametrize("preset", ["sharp", "soft", "softer"])
@pytest.mark.parametrize("name", list(SCENES))
def test_corners_and_joints_light_only_what_the_lamp_can_see(bench, name: str, preset: str) -> None:
    lamps, rects = SCENES[name]
    checked, wrong = _wrong(bench, lamps, rects, preset)
    # Pixels exactly on a shadow's edge round either way: well under 1%. The corner leak was ~50%.
    assert checked > 2000 and wrong <= checked * 0.01, f"{name} {preset}: {wrong} of {checked} pixels wrong"


def test_an_l_of_wall_tiles_is_not_shadowed_on_its_own_face(bench) -> None:
    from shadow_bench import Scene, light

    arm, foot = (288.0, 288.0, 32.0, 96.0), (288.0, 256.0, 128.0, 32.0)  # as the loader merges an L of tiles
    lamp = [light(470.0, 250.0, 300)]
    bench.load(Scene(lights=lamp, walls=[arm, foot]))
    shadowed = bench.frame()
    bench.load(Scene(lights=lamp, walls=[arm, foot], shadows="none"))
    plain = bench.frame()
    face = [(arm[0] + arm[2] * fx, arm[1] + arm[3] * fy) for fx in (0.2, 0.5, 0.8) for fy in (0.15, 0.5, 0.85)]
    worst = max(max(abs(a - b) for a, b in zip(bench.pixel(shadowed, pt), bench.pixel(plain, pt))) for pt in face)
    assert worst <= 2, f"the wall's face is darkened by its own shadow by up to {worst}"
