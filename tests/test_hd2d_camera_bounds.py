"""HD-2D follow camera bounds (settings.hd2d.camera.bounds): the game camera never shows past a room's edges, and keeps a
small room still and centred, unless the followed player would leave the picture: then the bounds give way by the least
move that shows the player (#774). Headless: the footprint arithmetic of engine.hd2d.renderer.fit_view, and the follow
camera's update on a stand-in renderer."""

from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Any

import pytest

from engine.hd2d.renderer import KEEP_MARGIN, Camera, Hd2dRenderer, fit_view
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


SHRINE_BOUNDS = (0.0, 0.0, 24.0, 24.0)  # the HD-2D room recipe's 24 x 24 m outdoor room (the #774 playtest room)


def _shrine() -> Camera:
    return Camera(30.0, 12.0, 53.518, False)


def _player(x: float, y: float) -> list[tuple[float, float, float]]:
    """A 32 x 48 px player's billboard corners standing at (x, y) m (feet and head; 1 / cos 30 stretch)."""
    head = 1.5 / math.cos(math.radians(30.0))
    return [(x + dx, y, z) for dx in (-0.5, 0.5) for z in (0.0, head)]


def _in_view(camera: Camera, target: tuple[float, float, float], body: list[tuple[float, float, float]]) -> bool:
    probe = Camera(camera.pitch, camera.fov, camera.distance, camera.ortho)
    probe.target = target
    vp = probe.view_projection(ASPECT)
    for p in body:
        c = [vp[i][0] * p[0] + vp[i][1] * p[1] + vp[i][2] * p[2] + vp[i][3] for i in range(4)]
        if c[3] <= 0 or max(abs(c[0] / c[3]), abs(c[1] / c[3])) > 1.0 - KEEP_MARGIN + 1e-9:
            return False
    return True


def _least_move(camera: Camera, start: tuple[float, float, float],
                body: list[tuple[float, float, float]]) -> tuple[float, float, float]:
    """The reference: the target nearest ``start`` that shows ``body``, by a coarse-to-fine grid search (0.4, 0.04,
    then 0.004 m) over the ground, independent of the closed form under test."""
    centre = start
    for step in (0.4, 0.04, 0.004):
        best = None
        for i in range(-20, 21):
            for j in range(-20, 21):
                t = (centre[0] + i * step, centre[1] + j * step, start[2])
                d = math.hypot(t[0] - start[0], t[1] - start[1])
                if (best is None or d < best[0]) and _in_view(camera, t, body):
                    best = (d, t)
        assert best is not None, "the player can be shown"
        centre = best[1]
    return centre


@pytest.mark.parametrize("feet", [(23.95, 23.81), (12.0, 23.81), (6.25, 23.81), (0.3, 12.0), (23.95, -0.1), (12.0, -0.1)],
                         ids=["ne_corner", "n_mid", "n_x6", "w_mid", "se_corner", "s_mid"])
def test_at_an_edge_the_bounds_give_way_by_the_least_move(feet: tuple[float, float]) -> None:
    """The view goes no further past the room than showing the player needs: the target is the one nearest the room's
    own (fitted) target that shows the player 5% inside the picture, not one centred on the player nor one along the
    way to it (which moves along the axis that needn't move, showing more of what lies past the room)."""
    camera, body = _shrine(), _player(*feet)
    goal = (feet[0], feet[1], 0.8)
    plain = fit_view(camera, goal, 0.0, SHRINE_BOUNDS, ASPECT)
    assert not _in_view(camera, plain, body), "the room's own picture leaves the player out (#774)"
    kept = fit_view(camera, goal, 0.0, SHRINE_BOUNDS, ASPECT, keep=body)
    least = _least_move(camera, plain, body)
    assert _in_view(camera, kept, body)
    moved, needed = math.dist(kept[:2], plain[:2]), math.dist(least[:2], plain[:2])
    assert abs(moved - needed) < 0.01, (kept, least, moved, needed)  # the least move (the grid's, to its 4 mm)
    assert math.dist(kept[:2], least[:2]) < 0.15, (kept, least)  # (where the edge it stops at is nearly flat)
    assert kept[2] == plain[2]


@pytest.mark.parametrize("feet", [(12.0, 12.0), (6.0, 8.0), (18.0, 16.0), (12.0, 4.0)])
def test_away_from_the_edges_the_picture_is_the_rooms_own(feet: tuple[float, float]) -> None:
    camera, goal = _shrine(), (feet[0], feet[1], 0.8)
    assert fit_view(camera, goal, 0.0, SHRINE_BOUNDS, ASPECT, keep=_player(*feet)) ==         fit_view(camera, goal, 0.0, SHRINE_BOUNDS, ASPECT)


def _renderer(bounds_px: tuple[float, float, float, float] | None, sprite: Any) -> Any:
    """What Hd2dRenderer.update reads, the follow camera settled at (12, 12) m: no particles, nothing moving."""
    camera = _shrine()
    camera.target = (12.0, 12.0, 0.8)
    settings = SimpleNamespace(camera=SimpleNamespace(height=0.8, bounds=bounds_px), ground=None)
    stand_in = SimpleNamespace(particles=None, moving=False, settings=settings, camera=camera, _camera_ready=True,
                               _aspect=ASPECT, followed=lambda: sprite, elevation_of=lambda s: 0.0)
    stand_in._body = lambda s: Hd2dRenderer._body(stand_in, s)
    return stand_in


def test_a_jump_in_a_room_without_bounds_is_simply_followed() -> None:
    """A room without camera bounds is as before: the follow camera eases toward the player (a 12 m teleport: 1/8 of
    the way, 1.5 m, in a 60th of a second), the player outside the picture meanwhile."""
    sprite = SimpleNamespace(center_x=24.0 * 32, bottom=12.0 * 32, width=32.0, height=48.0)
    r = _renderer(None, sprite)
    Hd2dRenderer.update(r, 1 / 60)
    k = 1.0 - math.exp(-8.0 / 60)
    assert r.camera.target == pytest.approx((12.0 + 12.0 * k, 12.0, 0.8))
    assert r.camera.target[0] - 12.0 == pytest.approx(1.5, abs=0.01)


def test_a_jump_in_a_bounded_room_keeps_the_player_in_the_picture_at_once() -> None:
    """With bounds, the player never leaves the picture, even for a frame after a jump to the room's edge."""
    sprite = SimpleNamespace(center_x=23.95 * 32, bottom=12.0 * 32, width=32.0, height=48.0)
    r = _renderer((0.0, 0.0, 768.0, 768.0), sprite)
    Hd2dRenderer.update(r, 1 / 60)
    assert _in_view(r.camera, r.camera.target, _player(23.95, 12.0))
