"""HD-2D follow camera bounds (settings.hd2d.camera.bounds): the game camera never shows past a room's edges, and keeps a
small room still and centred. Headless: the footprint arithmetic of engine.hd2d.renderer.fit_view."""

from __future__ import annotations

import math

import pytest

from engine.hd2d.renderer import KEEP_MARGIN, Camera, fit_view
from engine.hd2d.settings import Hd2dSettingsError, parse_hd2d

pytestmark = pytest.mark.fast

ASPECT = 16 / 9


def _footprint(camera: Camera, target: tuple[float, float, float], floor: float = 0.0) -> tuple[float, ...]:
    """The floor the picture shows (m): min x, min y, max x, max y."""
    camera.target = target
    xs, ys = [], []
    for nx, ny in ((-1.0, -1.0), (1.0, -1.0), (-1.0, 1.0), (1.0, 1.0)):
        origin, d = camera.ray(nx, ny, ASPECT)
        t = (floor - origin[2]) / d[2]
        xs.append(origin[0] + d[0] * t)
        ys.append(origin[1] + d[1] * t)
    return min(xs), min(ys), max(xs), max(ys)


@pytest.mark.parametrize("camera", [Camera(30.0, 30.0, 21.0, True), Camera(30.0, 12.0, 53.5, False)],
                         ids=["ortho", "narrow"])
def test_the_picture_stays_inside_a_large_room(camera: Camera) -> None:
    bounds = (0.0, 0.0, 40.0, 32.0)
    for x, y in ((20.0, 16.0), (1.0, 1.0), (39.0, 31.0), (20.0, 28.0)):
        goal = fit_view(camera, (x, y, 0.8), 0.0, bounds, ASPECT)
        x0, y0, x1, y1 = _footprint(camera, goal)
        assert x0 >= -1e-6 and y0 >= -1e-6 and x1 <= 40 + 1e-6 and y1 <= 32 + 1e-6, (x, y, goal)
    middle = fit_view(camera, (20.0, 16.0, 0.8), 0.0, bounds, ASPECT)
    assert middle == pytest.approx((20.0, 16.0, 0.8)), "well inside, it simply follows"


def test_a_small_room_is_centred_and_still() -> None:
    camera = Camera(50.0, 12.0, 40.0, False)
    bounds = (4.5, 3.0, 11.5, 9.0)
    goals = {fit_view(camera, (x, y, 0.9), 0.1, bounds, ASPECT) for x, y in ((5.0, 4.0), (10.0, 8.0), (8.0, 6.0))}
    assert len(goals) == 1, "wherever the player stands, the picture is the same"
    x0, y0, x1, y1 = _footprint(camera, goals.pop(), 0.1)
    assert (x0 + x1) / 2 == pytest.approx(8.0) and (y0 + y1) / 2 == pytest.approx(6.0), "the room in the middle"


def test_a_picture_that_reaches_the_horizon_is_left_alone() -> None:
    camera = Camera(10.0, 30.0, 20.0, False)  # its top edge looks above the horizon
    assert fit_view(camera, (1.0, 1.0, 0.8), 0.0, (0.0, 0.0, 40.0, 32.0), ASPECT) == (1.0, 1.0, 0.8)


def test_bounds_are_validated() -> None:
    assert parse_hd2d({"camera": {"bounds": [0, 0, 1280, 1024]}}).camera.bounds == (0.0, 0.0, 1280.0, 1024.0)
    assert parse_hd2d({}).camera.bounds is None, "existing rooms simply follow"
    for bad in ([0, 0, 10], [10, 0, 0, 10], ["a", 0, 1, 1], [0, 0, float("inf"), 1]):
        with pytest.raises(Hd2dSettingsError, match="camera.bounds"):
            parse_hd2d({"camera": {"bounds": bad}})


def test_the_bounds_give_way_to_keep_the_player_in_the_picture() -> None:
    """A 24 x 24 m room whose picture of the floor is as large as it (the HD-2D room recipe's outdoor camera): kept
    inside the room the camera can't move, and the picture, a tilted trapezoid narrower near the camera, leaves a
    player at the sides out of it, and one at the far edge standing above it. Given the player's body, the bounds give
    way; well inside, nothing changes."""
    camera, bounds = Camera(30.0, 12.0, 53.518, False), (0.0, 0.0, 24.0, 24.0)
    head = 1.5 / math.cos(math.radians(30.0))
    for x, y in ((0.3, 0.0), (23.7, 0.0), (0.3, 12.0), (23.7, 12.0), (12.0, 23.7), (0.3, 23.7), (23.7, 23.7), (12.0, 0.0)):
        body = [(x + dx, y, z) for dx in (-0.5, 0.5) for z in (0.0, head)]
        camera.target = fit_view(camera, (x, y, 0.8), 0.0, bounds, ASPECT, keep=body)
        vp = camera.view_projection(ASPECT)
        for p in body:
            c = [vp[i][0] * p[0] + vp[i][1] * p[1] + vp[i][2] * p[2] + vp[i][3] for i in range(4)]
            assert max(abs(c[0] / c[3]), abs(c[1] / c[3])) <= 1.0 - KEEP_MARGIN + 1e-6, (x, y, p)
    body = [(12.0 + dx, 12.0, z) for dx in (-0.5, 0.5) for z in (0.0, head)]
    kept = fit_view(camera, (12.0, 12.0, 0.8), 0.0, bounds, ASPECT, keep=body)
    assert kept == fit_view(camera, (12.0, 12.0, 0.8), 0.0, bounds, ASPECT), "a player in view: the picture as before"
