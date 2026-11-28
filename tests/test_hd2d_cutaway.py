"""HD-2D cutaway, headless: the per-structure ``cutaway`` setting is validated where rooms are read and where they are
edited (project_ops.set_structure: Mesh Studio's See-through button, AI tools). The rendering is
tests/test_hd2d_cutaway_gpu.py."""

from __future__ import annotations

from typing import Any

import pytest

from engine import project_ops as ops
from engine.hd2d.settings import Hd2dSettingsError, parse_hd2d

pytestmark = pytest.mark.fast

MODEL = "assets/models/cottage.glb"


def test_cutaway_is_off_unless_a_structure_asks_for_it() -> None:
    hd = parse_hd2d({"structures": [{"id": "a", "model": MODEL}, {"id": "b", "model": MODEL, "cutaway": True}]})
    assert [(st.id, st.cutaway) for st in hd.structures] == [("a", False), ("b", True)]
    with pytest.raises(Hd2dSettingsError, match="cutaway must be true or false"):
        parse_hd2d({"structures": [{"id": "a", "model": MODEL, "cutaway": "yes"}]})


def test_the_edit_turns_it_on_and_off_and_refuses_anything_else() -> None:
    scene = {"entities": [], "settings": {"hd2d": {"structures": [{"id": "house", "model": MODEL, "x": 64, "y": 64}]}}}
    on = ops.set_structure(scene, "house", cutaway=True)
    assert ops.find_structure(on, "house")["cutaway"] is True
    off = ops.set_structure(on, "house", cutaway=False)
    assert "cutaway" not in ops.find_structure(off, "house"), "off is the default: nothing written"
    assert ops.set_structure(scene, "house", x=96)["settings"]["hd2d"]["structures"][0].get("cutaway") is None
    with pytest.raises(ops.OpError, match="cutaway must be true or false"):
        ops.set_structure(scene, "house", cutaway=1)


# ---- the cut's rule (renderer.cutaway_cuts, MESH_FS's CPU twin): only what covers the followed character's picture

Vec = tuple[float, float, float]


def _scene(pitch: float = 30.0, ortho: bool = False) -> tuple[Any, Vec, Vec, tuple[float, float], Vec, Vec]:
    from types import SimpleNamespace

    from engine.hd2d.renderer import Camera, cutaway_box

    sprite = SimpleNamespace(width=32.0, height=48.0, center_x=320.0, bottom=320.0)  # 1 m x 1.5 m at (10, 10) m
    middle, half = cutaway_box(sprite, 0.0, pitch)
    cam = Camera(pitch, 12.0, 53.518, ortho)
    cam.target = middle
    eye = cam.eye()
    sight = [middle[i] - eye[i] for i in range(3)]
    n = sum(v * v for v in sight) ** 0.5
    d = tuple(v / n for v in sight)
    up = (cam.right()[1] * d[2] - cam.right()[2] * d[1], cam.right()[2] * d[0] - cam.right()[0] * d[2],
          cam.right()[0] * d[1] - cam.right()[1] * d[0])
    return cam, eye, middle, half, d, up


def _cuts(point: Vec, pitch: float = 30.0, ortho: bool = False) -> bool:
    from engine.hd2d.renderer import cutaway_cuts

    cam, eye, middle, half, d, _up = _scene(pitch, ortho)
    return cutaway_cuts(point, eye=eye, middle=middle, right=cam.right(), half=half, floor_m=0.0, ortho=ortho,
                        forward=d if ortho else None)


def _at(front: float, across: float = 0.0, upward: float = 0.0, pitch: float = 30.0, ortho: bool = False) -> Vec:
    """A point ``front`` m nearer the camera than the character's middle along the line of sight, offset ``across``
    (the camera's right) and ``upward`` (up the picture) m, as seen at the character's distance (cone-scaled)."""
    _cam, eye, middle, _half, d, up = _scene(pitch, ortho)
    reach = sum((middle[i] - eye[i]) ** 2 for i in range(3)) ** 0.5
    k = 1.0 if ortho else (reach - front) / reach
    right = _cam.right()
    return tuple(middle[i] - d[i] * front + (right[i] * across + up[i] * upward) * k for i in range(3))


def test_the_box_is_the_characters_picture_plus_the_margin() -> None:
    from types import SimpleNamespace

    from engine.hd2d.renderer import CUTAWAY_MARGIN, cutaway_box

    sprite = SimpleNamespace(width=32.0, height=48.0, center_x=320.0, bottom=160.0)
    middle, half = cutaway_box(sprite, 0.5, 60.0)  # stretched by 1 / cos 60 = 2: the billboard stands 3 m tall
    assert middle == pytest.approx((10.0, 5.0, 0.5 + 1.5))
    assert half == pytest.approx((0.5 + CUTAWAY_MARGIN, 0.75 + CUTAWAY_MARGIN))


def test_a_roof_in_front_of_the_character_is_cut_only_over_its_picture() -> None:
    assert _cuts(_at(3.0)), "in front, on the line of sight"
    assert _cuts(_at(3.0, across=0.6)) and _cuts(_at(3.0, upward=0.9)), "inside the box (sprite + margin)"
    assert not _cuts(_at(3.0, across=0.9)) and not _cuts(_at(3.0, upward=1.4)), "beside or above it: drawn"


def test_only_what_is_in_front_and_above_the_floor_is_cut() -> None:
    assert not _cuts(_at(-1.0)), "behind the character"
    assert not _cuts(_at(0.15)) and _cuts(_at(0.3)), "the 0.2 m in front of its middle is kept (as before)"
    low = _at(3.0)
    assert not _cuts((low[0], low[1], 0.04)), "at or below the floor (+0.05 m)"


def test_the_opening_is_a_cone_matching_the_picture_not_a_cylinder() -> None:
    from engine.hd2d.renderer import cutaway_cuts

    cam, eye, middle, half, d, _up = _scene()
    reach = sum((middle[i] - eye[i]) ** 2 for i in range(3)) ** 0.5
    halfway = tuple(eye[i] + d[i] * reach / 2 for i in range(3))
    side = tuple(halfway[i] + cam.right()[i] * 0.5 for i in range(3))  # 0.5 m off the line halfway: 1 m in the picture
    assert not cutaway_cuts(side, eye=eye, middle=middle, right=cam.right(), half=half, floor_m=0.0)
    near = tuple(halfway[i] + cam.right()[i] * 0.3 for i in range(3))  # 0.6 m in the picture: inside
    assert cutaway_cuts(near, eye=eye, middle=middle, right=cam.right(), half=half, floor_m=0.0)


def test_its_corners_are_rounded() -> None:
    from engine.hd2d.renderer import CUTAWAY_CORNER, CUTAWAY_MARGIN

    hx, hy = 0.5 + CUTAWAY_MARGIN, 0.75 + CUTAWAY_MARGIN
    assert _cuts(_at(3.0, across=hx - 0.02, upward=0.0)) and _cuts(_at(3.0, across=0.0, upward=hy - 0.02))
    assert not _cuts(_at(3.0, across=hx - 0.03, upward=hy - 0.03)), "the corner itself is rounded off"
    assert _cuts(_at(3.0, across=hx - CUTAWAY_CORNER, upward=hy - CUTAWAY_CORNER))


def test_an_orthographic_camera_cuts_a_prism_the_same_size_at_every_depth() -> None:
    assert _cuts(_at(20.0, across=0.6, ortho=True), ortho=True) and not _cuts(_at(20.0, across=0.9, ortho=True), ortho=True)


@pytest.mark.parametrize("pitch", [30.0, 35.0, 40.0, 55.0])
def test_what_it_cuts_lies_inside_the_characters_box_in_the_picture(pitch: float) -> None:
    """Points the rule cuts, projected with the camera's own view-projection, fall inside the picture of the box
    (sprite + margin) at the character's distance: the opening is where the character is drawn, at every pitch."""
    import random

    from engine.hd2d.renderer import cutaway_cuts

    cam, eye, middle, half, d, up = _scene(pitch)
    vp = cam.view_projection(16 / 9)

    def ndc(p: Vec) -> tuple[float, float]:
        x, y, z = p
        c = [vp[r][0] * x + vp[r][1] * y + vp[r][2] * z + vp[r][3] for r in range(4)]
        return c[0] / c[3], c[1] / c[3]

    right = cam.right()
    corners = [ndc(tuple(middle[i] + right[i] * sx * half[0] + up[i] * sy * half[1] for i in range(3)))
               for sx in (-1, 1) for sy in (-1, 1)]
    x0, x1 = min(c[0] for c in corners), max(c[0] for c in corners)
    y0, y1 = min(c[1] for c in corners), max(c[1] for c in corners)
    rng = random.Random(7)
    cut = 0
    for _ in range(4000):
        f = rng.uniform(0.3, 30.0)
        p = tuple(middle[i] - d[i] * f + right[i] * rng.uniform(-3, 3) + up[i] * rng.uniform(-3, 3) for i in range(3))
        if p[2] > 0.05 and cutaway_cuts(p, eye=eye, middle=middle, right=right, half=half, floor_m=0.0):
            cut += 1
            px, py = ndc(p)
            assert x0 - 1e-6 <= px <= x1 + 1e-6 and y0 - 1e-6 <= py <= y1 + 1e-6, (p, px, py)
    assert cut > 100
