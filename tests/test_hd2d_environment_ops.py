"""Milestone 22A: an HD-2D room made in Mesh Studio (its size), its gameplay camera, and its sun, ambient light and sky:
the operations Studio and AI tools edit through. Headless."""

from __future__ import annotations

import math

import pytest

import engine.project_ops as ops
from engine.hd2d.settings import parse_hd2d

pytestmark = pytest.mark.fast

PATH = "packs/core_regions/scenes/meadow.json"


def _room(width: float = 40, depth: float = 30, *, outdoor: bool = True) -> dict:
    scene, _map_path, _skeleton = ops.make_hd2d_room({"name": "Meadow", "entities": []}, PATH, width, depth,
                                                     outdoor=outdoor)
    return scene


def test_a_new_hd2d_room_is_the_templates_own_recipe_at_its_size() -> None:
    from engine.hd2d.starter_village import INDOOR_VIEW, OUTDOOR_VIEW, _camera, _hd2d

    outdoor, indoor = _room(), _room(16, 12, outdoor=False)
    assert outdoor["settings"]["hd2d"] == _hd2d(40, 30, _camera(30.0, OUTDOOR_VIEW, (0, 0, 40, 30)))
    expected = _hd2d(16, 12, _camera(55.0, INDOOR_VIEW, (0, 0, 16, 12)), ambient=0.55, sky="#120e0b")
    assert indoor["settings"]["hd2d"] == expected
    assert (outdoor["settings"]["world_width"], outdoor["settings"]["world_height"]) == (1280.0, 960.0)
    assert outdoor["tilemap"]["width"] == 40 and outdoor["tilemap"]["height"] == 30  # a plain map of its size
    parse_hd2d(outdoor["settings"]["hd2d"])


def test_a_new_hd2d_room_replaces_a_2d_map_and_refuses_odd_sizes() -> None:
    scene, _path, _skeleton = ops.add_map({"name": "R", "entities": []}, PATH, width=20, height=15,
                                          ground=ops.STARTER_FLOOR, border=ops.STARTER_WALL)
    scene, _path, _skeleton = ops.make_hd2d_room(scene, PATH, 24, 18)
    assert scene["tilemap"]["width"] == 24
    for bad in (4, 300, "wide", True, math.nan):
        with pytest.raises(ops.OpError, match="8 to 256 m"):
            ops.make_hd2d_room({"name": "R", "entities": []}, PATH, bad, 20)


def test_the_camera_is_set_in_what_the_player_sees() -> None:
    scene = _room()
    assert ops.hd2d_camera_of(scene)["view"] == pytest.approx(11.25) and ops.hd2d_camera_of(scene)["pitch"] == 30
    scene = ops.set_hd2d_camera(scene, view=15, pitch=45, height=1.2)
    cam = ops.hd2d_camera_of(scene)
    assert (cam["view"], cam["pitch"], cam["height"]) == (pytest.approx(15.0), 45.0, 1.2)
    raw = scene["settings"]["hd2d"]["camera"]
    assert raw["distance"] == pytest.approx(15 / 2 / math.tan(math.radians(6)), abs=1e-3)  # the view at its lens
    assert raw["follow"] == "player" and raw["bounds"] == [0.0, 0.0, 1280.0, 960.0]
    scene = ops.set_hd2d_camera(scene, bounded=False)
    assert "bounds" not in scene["settings"]["hd2d"]["camera"]
    scene = ops.set_hd2d_camera(scene, bounded=True)  # back: the room's ground
    assert scene["settings"]["hd2d"]["camera"]["bounds"] == [0.0, 0.0, 1280.0, 960.0]
    for preset, values in ops.CAMERA_PRESETS.items():
        cam = ops.hd2d_camera_of(ops.set_hd2d_camera(scene, preset=preset))
        assert cam["view"] == pytest.approx(values["view"]) and cam["pitch"] == values["pitch"], preset
    for bad, reason in (({"pitch": 95}, "pitch"), ({"view": 1}, "view must be 2 to 200"), ({"ortho": "yes"}, "true or false"),
                        ({"preset": "drone"}, "preset must be")):
        with pytest.raises(ops.OpError, match=reason):
            ops.set_hd2d_camera(scene, **bad)


def test_the_sun_is_set_by_where_it_is_in_the_sky() -> None:
    scene = _room()
    sun = ops.hd2d_sun_of(scene)  # Mesh's default: high in the south-west
    assert (sun["azimuth"], sun["elevation"], sun["color"], sun["ambient"], sun["sky"]) == (
        pytest.approx(219.3, abs=0.1), pytest.approx(44.6, abs=0.1), "#fff0d8", 0.45, "#76a0d6")
    scene = ops.set_hd2d_sun(scene, azimuth=90, elevation=30, color="#ffcc88", intensity=0.8, ambient=0.3, sky="#204060")
    raw = scene["settings"]["hd2d"]
    assert raw["sun"]["direction"] == pytest.approx([math.cos(math.radians(30)), 0.0, 0.5], abs=1e-4)  # from the east
    assert (raw["sun"]["color"], raw["sun"]["intensity"], raw["ambient"], raw["sky"]) == ("#ffcc88", 0.8, 0.3, "#204060")
    sun = ops.hd2d_sun_of(scene)
    assert (sun["azimuth"], sun["elevation"]) == (pytest.approx(90.0), pytest.approx(30.0))
    parsed = parse_hd2d(raw)
    assert parsed.sun_intensity == 0.8 and parsed.ambient == 0.3
    for preset in ops.SUN_PRESETS:
        parse_hd2d(ops.set_hd2d_sun(scene, preset=preset)["settings"]["hd2d"])
    for bad, reason in (({"elevation": 2}, "elevation"), ({"intensity": 20}, "intensity"), ({"color": "warm"}, "colour"),
                        ({"sky": 3}, "sky must be"), ({"preset": "dusk"}, "preset must be")):
        with pytest.raises(ops.OpError, match=reason):
            ops.set_hd2d_sun(scene, **bad)


def test_a_2d_room_has_no_camera_or_sun_to_set() -> None:
    for op in (ops.set_hd2d_camera, ops.set_hd2d_sun):
        with pytest.raises(ops.OpError, match="isn't an HD-2D room"):
            op({"name": "R", "entities": [], "settings": {}}, preset="noon" if op is ops.set_hd2d_sun else "outdoor")


def test_a_new_hd2d_rooms_player_starts_in_its_middle() -> None:
    """A 2D room's player starts near its corner; in an HD-2D room the camera keeps inside the room, so a corner start
    squeezed the player into the picture's edge."""
    scene = {"name": "R", "entities": [{"id": "r_player", "prefab_id": "player", "x": 128.0, "y": 128.0}]}
    scene, _path, _skeleton = ops.make_hd2d_room(scene, PATH, 40, 30)
    assert (scene["entities"][0]["x"], scene["entities"][0]["y"]) == (640.0, 480.0)


def _floor_seen(view, aspect: float) -> tuple[float, float, float, float]:
    """Where the picture's four corners meet the floor (z = 0): x0, y0, x1, y1 in m."""
    xs, ys = [], []
    for nx, ny in ((-1.0, -1.0), (1.0, -1.0), (-1.0, 1.0), (1.0, 1.0)):
        origin, d = view.ray(nx, ny, aspect)
        t = -origin[2] / d[2]
        xs.append(origin[0] + d[0] * t)
        ys.append(origin[1] + d[1] * t)
    return min(xs), min(ys), max(xs), max(ys)


def _with_player(scene: dict, x: float, y: float) -> dict:
    scene["entities"] = [{"id": "r_player", "tag": "player", "x": x, "y": y}]
    return scene


def test_see_it_keeps_the_game_camera_inside_the_room_near_its_edge() -> None:
    """Studio's "See it" shows what play shows: the follow camera's own ``fit_view`` at the preview's shape."""
    from engine.studio_hd2d import game_view

    aspect = 1.6
    scene = _with_player(_room(), 32.0, 32.0)  # 1 m from the room's south-west corner
    view = game_view(scene, aspect)
    assert view.target[0] > 1.0 and view.target[1] > 1.0  # moved in from the player
    x0, y0, x1, y1 = _floor_seen(view, aspect)
    assert x0 == pytest.approx(0.0, abs=1e-6) and y0 == pytest.approx(0.0, abs=1e-6)  # the edge, not past it
    assert x1 < 40 and y1 < 30
    middle = game_view(_with_player(_room(120, 90), 1920.0, 1440.0), aspect)  # far from the edges: on the player
    assert middle.target[:2] == pytest.approx((60.0, 45.0))


def test_see_it_centres_a_room_smaller_than_the_picture() -> None:
    from engine.studio_hd2d import game_view

    aspect = 1.6
    scene = ops.set_hd2d_camera(_with_player(_room(8, 8), 40.0, 40.0), preset="wide")  # 18 m view of an 8 m room
    x0, y0, x1, y1 = _floor_seen(game_view(scene, aspect), aspect)
    assert x1 - x0 > 8 and (x0 + x1) / 2 == pytest.approx(4.0, abs=1e-6)
    assert (y0 + y1) / 2 == pytest.approx(4.0, abs=1e-6)


def test_see_it_with_an_unbounded_camera_stays_on_the_player() -> None:
    from engine.studio_hd2d import game_view

    scene = ops.set_hd2d_camera(_with_player(_room(), 32.0, 32.0), bounded=False, height=1.2)
    view = game_view(scene, 1.6)
    assert view.target == pytest.approx((1.0, 1.0, 1.2))
    assert (view.pitch, view.yaw) == (30.0, 0.0)
