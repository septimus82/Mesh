"""A 2D room's edges stop its movers as walls do: nobody walks off the map into the void (round-3 audit #751).

Only the camera used to be kept in the room. Now the player (engine.physics_runtime.move_entity_with_physics) and every
SceneController mover (enemies, patrols, followers, cutscene moves: move_entity_with_collision) stop flush with the
edge of the same rectangle the camera is kept in (CameraController.world_rect, through physics_runtime.room_bounds).
A room with no size, and an HD-2D room (its floors bound it: World.move), are not kept.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine.camera_controller import CameraController
from engine.physics_model import Aabb, entity_aabb, keep_inside
from engine.physics_runtime import move_entity_with_physics, room_bounds

pytestmark = pytest.mark.fast

ROOM = (0.0, 0.0, 768.0, 512.0)  # a blank room: 24 x 16 tiles of 32 px, no walls


class _Sprite:
    """What the movers read from an Arcade sprite."""

    def __init__(self, x: float, y: float, w: float = 20.0, h: float = 20.0, data: dict | None = None) -> None:
        self.center_x, self.center_y, self.width, self.height = x, y, w, h
        self.mesh_entity_data = data or {}

    left = property(lambda s: s.center_x - s.width / 2)
    right = property(lambda s: s.center_x + s.width / 2)
    bottom = property(lambda s: s.center_y - s.height / 2)
    top = property(lambda s: s.center_y + s.height / 2)


def _walk(sprite: _Sprite, step: tuple[float, float], frames: int, bounds=ROOM) -> None:
    for _ in range(frames):
        move_entity_with_physics(sprite, step, [], bounds)


@pytest.mark.parametrize(("step", "edge"), [((-2.5, 0.0), "left"), ((2.5, 0.0), "right"),
                                            ((0.0, -2.5), "bottom"), ((0.0, 2.5), "top")])
def test_walking_off_each_edge_stops_flush(step: tuple[float, float], edge: str) -> None:
    sprite = _Sprite(128.0, 128.0)
    _walk(sprite, step, 600)  # 1500 px: far past every edge
    expected = {"left": ROOM[0], "bottom": ROOM[1], "right": ROOM[2], "top": ROOM[3]}[edge]
    assert getattr(sprite, edge) == pytest.approx(expected), "it walked off the map"
    _walk(sprite, (-step[0], -step[1]), 4)
    assert getattr(sprite, edge) == pytest.approx(expected - 4 * (step[0] + step[1])), "and walks straight back"


def test_diagonal_into_a_corner_stops_flush_on_both_edges_and_slides_along() -> None:
    sprite = _Sprite(700.0, 450.0)
    _walk(sprite, (1.8, 1.8), 200)
    assert (sprite.right, sprite.top) == (pytest.approx(768.0), pytest.approx(512.0))
    _walk(sprite, (-1.8, 1.8), 10)  # along the top edge: free sideways, still flush
    assert sprite.top == pytest.approx(512.0) and sprite.right == pytest.approx(768.0 - 18.0)


@pytest.mark.parametrize("step", [400.0, 1e5])  # a slow frame: one move far past the edge (beyond the 256-piece cap)
def test_a_move_of_any_length_ends_at_the_edge(step: float) -> None:
    for delta, edge, expected in (((step, 0.0), "right", 768.0), ((-step, 0.0), "left", 0.0),
                                  ((0.0, step), "top", 512.0), ((0.0, -step), "bottom", 0.0),
                                  ((step, -step), "right", 768.0)):
        sprite = _Sprite(384.0, 256.0)
        result = move_entity_with_physics(sprite, delta, [], ROOM)
        assert getattr(sprite, edge) == pytest.approx(expected), (delta, edge)
        assert result.final_pos == (sprite.center_x, sprite.center_y)


def test_the_collider_is_kept_inside_not_the_picture() -> None:
    """A feet collider (box, offset down) stops flush with the edge; the picture above it may overlap the top edge."""
    feet = {"components": {"collider": {"kind": "box", "w": 16, "h": 8, "offset_x": 0, "offset_y": -12}}}
    sprite = _Sprite(384.0, 256.0, 32.0, 32.0, feet)
    _walk(sprite, (0.0, 5.0), 200)
    assert entity_aabb(sprite).top == pytest.approx(512.0) and sprite.top > 512.0
    _walk(sprite, (5.0, -5.0), 400)
    box = entity_aabb(sprite)
    assert (box.right, box.bottom) == (pytest.approx(768.0), pytest.approx(0.0))


def test_a_room_with_no_size_is_not_kept() -> None:
    sprite = _Sprite(128.0, 128.0)
    _walk(sprite, (0.0, -2.5), 400, bounds=None)
    assert sprite.center_y == pytest.approx(128.0 - 1000.0), "an unsized room is open: no edge"
    assert keep_inside(Aabb(-50.0, 900.0, 20, 20), (-3.0, 3.0), None) == (-50.0, 900.0)


def test_a_mover_put_outside_walks_back_in_and_never_further_out() -> None:
    sprite = _Sprite(128.0, -300.0)  # a spawn point / teleport below the room
    _walk(sprite, (2.0, 0.0), 5)
    assert (sprite.center_x, sprite.center_y) == (pytest.approx(138.0), -300.0), "along the edge: free, no snap"
    _walk(sprite, (0.0, 3.0), 10)
    assert sprite.center_y == pytest.approx(-270.0), "back toward the room: free"
    _walk(sprite, (0.0, -3.0), 1)
    assert sprite.bottom == pytest.approx(0.0), "further out: stopped at the edge, as a wall it stands in"


def _camera(world_w, world_h, bounds=None) -> CameraController:
    camera = object.__new__(CameraController)  # (world_rect reads only these)
    camera.window = SimpleNamespace(world_width=world_w, world_height=world_h, width=640, height=480)
    camera.bounds = bounds
    return camera


def test_the_rectangle_is_the_cameras() -> None:
    assert _camera(768, 512).world_rect() == ROOM, "the world size"
    assert _camera(1000, 1000, (0.0, 0.0, 768.0, 512.0)).world_rect() == ROOM, \
        "camera bounds win (a tilemap's size, or the scene's camera.bounds), as clamp_camera_to_world"
    for w, h in ((None, None), (768, None), (0, 512), (-5, 512)):
        assert _camera(w, h).world_rect() is None, (w, h)


def test_room_bounds_for_a_2d_room_only() -> None:
    window = SimpleNamespace(hd2d_world=None, camera_controller=_camera(768, 512))
    assert room_bounds(window) == ROOM
    assert room_bounds(SimpleNamespace(hd2d_world=object(), camera_controller=_camera(768, 512))) is None, \
        "HD-2D: World.move's floors bound it"
    assert room_bounds(SimpleNamespace(hd2d_world=None, camera_controller=_camera(None, None))) is None
    assert room_bounds(SimpleNamespace()) is None and room_bounds(None) is None


def _overlap(a, others):
    return [o for o in others if a.right > o.left and a.left < o.right and a.top > o.bottom and a.bottom < o.top]


def test_scene_controller_movers_are_kept_inside_too(monkeypatch: pytest.MonkeyPatch) -> None:
    import engine.scene_controller_core as core
    from engine.scene_controller_parts.gameplay_runtime import move_entity_with_collision

    monkeypatch.setattr(core.optional_arcade, "arcade", SimpleNamespace(check_for_collision_with_list=_overlap))
    window = SimpleNamespace(hd2d_world=None, camera_controller=_camera(768, 512))
    controller = SimpleNamespace(solid_sprites=[], window=window)
    enemy = _Sprite(700.0, 40.0)
    for _ in range(100):
        move_entity_with_collision(controller, enemy, 3.0, -3.0)
    assert (enemy.right, enemy.bottom) == (pytest.approx(768.0), pytest.approx(0.0)), "an enemy walked off the map"
    move_entity_with_collision(controller, enemy, -5000.0, 0.0)  # a fast move, cut in pieces
    assert enemy.left == pytest.approx(0.0)
    wall = _Sprite(30.0, 256.0, 20.0, 100.0)  # a wall short of the edge still stops it first
    controller.solid_sprites = [wall]
    enemy.center_x, enemy.center_y = 200.0, 256.0
    move_entity_with_collision(controller, enemy, -5000.0, 0.0)
    assert enemy.left == pytest.approx(wall.right)
    open_room = SimpleNamespace(solid_sprites=[], window=SimpleNamespace(hd2d_world=None,
                                                                        camera_controller=_camera(None, None)))
    move_entity_with_collision(open_room, enemy, 0.0, -1000.0)
    assert enemy.center_y == pytest.approx(-744.0), "a room with no size: not kept"
