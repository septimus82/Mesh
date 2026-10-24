"""Milestone 16 Stage 1: real 3D geometry and 2D characters in one depth-tested scene (tooling/hd2d_lab).
Rendered off-screen in a hidden window. GL-gated: set MESH_GL_SMOKE=1."""

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

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))
np = pytest.importorskip("numpy")


@pytest.fixture(scope="module")
def lab():
    from hd2d_lab.lab import Lab
    from shadow_bench import Bench

    bench = Bench()  # a hidden window and its GL context
    lab = Lab(window=bench.window)
    lab.load_structure()
    yield lab
    bench.close()


def test_a_character_is_hidden_behind_the_building_and_drawn_over_it_in_front(lab) -> None:
    from hd2d_lab.lab import Character

    front, behind = Character("hero", 0.2, -3.2, 0.0, "up"), Character("hero", 0.0, 2.5, 0.0, "down")
    assert lab.total_pixels(front) > 1500 and lab.visible_pixels(front) == lab.total_pixels(front)
    assert lab.total_pixels(behind) > 1500 and lab.visible_pixels(behind) == 0, "fully behind the hut: depth hides it"
    corner = Character("hero", 2.25, 1.6, 0.0, "up")
    assert 0 < lab.visible_pixels(corner) < lab.total_pixels(corner), "half behind the corner: partly hidden"


def test_a_character_on_the_raised_platform_stands_on_it(lab) -> None:
    from hd2d_lab.lab import Character

    # The same spot east of the platform (free ground) at height 0, and the villager on the platform 1 m up.
    ground, raised = Character("villager", 3.4, -0.6, 0.0), Character("villager", 1.6, -0.6, 1.0)
    image = lambda c: np.asarray(lab.render([], solid=c))[:, :, 0] > 200  # noqa: E731
    rows = lambda mask: np.nonzero(mask.any(axis=1))[0]  # noqa: E731
    assert lab.visible_pixels(raised) == lab.total_pixels(raised), "on top of the platform: nothing hides it"
    assert rows(image(raised)).max() < rows(image(ground)).max() - 20, "its feet are drawn higher: 1 m up"


def test_pixel_art_textures_are_sampled_without_blending(lab) -> None:
    from hd2d_lab.lab import ASSETS
    from PIL import Image

    with Image.open(ASSETS / "stone_wall.png") as texture:
        palette = {px[:3] for px in texture.convert("RGBA").getdata()}
    lab.lit = False
    try:
        frame = np.asarray(lab.render([]))
    finally:
        lab.lit = True
    wall = frame[230:250, 420:540].reshape(-1, 3)  # the hut's south wall, facing the camera
    colours = {tuple(int(v) for v in c) for c in wall}
    assert len(colours) >= 3 and colours <= palette, "only the texture's own colours: no bilinear mixing"
