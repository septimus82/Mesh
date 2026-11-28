"""A cutscene's move_to toward a point it can't reach (past a 2D room's edge, behind a wall) ends where it is blocked.

It used to finish only within ``tolerance`` of its target, so a blocked mover waited for good, and with
``lock_player_input`` the player stayed locked for good (#770 review: an NPC at x=600 in a 768 px room, move_to
x=900, stuck at x=752 after 30 s). Now not moving for SequencePlayer.BLOCKED_S ends the step where it stands; the
sequence goes on, and its end releases the lock.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine.behaviours.sequence_player import BLOCKED_S, SequencePlayer

pytestmark = [pytest.mark.fast]


class _Sprite:
    def __init__(self, x: float, y: float, w: float = 32.0, h: float = 32.0) -> None:
        self.center_x, self.center_y, self.width, self.height = x, y, w, h
        self.mesh_name, self.mesh_entity_data = "guide", {}

    left = property(lambda s: s.center_x - s.width / 2)
    right = property(lambda s: s.center_x + s.width / 2)
    bottom = property(lambda s: s.center_y - s.height / 2)
    top = property(lambda s: s.center_y + s.height / 2)


def _overlap(a, others):
    return [o for o in others if a.right > o.left and a.left < o.right and a.top > o.bottom and a.bottom < o.top]


class _Window:
    """A 2D room 768 x 512 px (the camera's rectangle) moving through the SceneController mover, with input locks."""

    def __init__(self, walls: list[_Sprite]) -> None:
        from engine.scene_controller_parts.gameplay_runtime import move_entity_with_collision

        camera = SimpleNamespace(world_rect=lambda: (0.0, 0.0, 768.0, 512.0))
        self.hd2d_world, self.camera_controller = None, camera
        self.scene = SimpleNamespace(solid_sprites=walls, window=self)
        self._move = move_entity_with_collision
        self.locks: list[str] = []
        self.signals: list[str] = []

    def move_entity_with_collision(self, sprite, dx: float, dy: float, friction: float = 1.0) -> None:
        self._move(self.scene, sprite, dx, dy, friction)

    def lock_player_input(self, owner: str) -> None:
        self.locks.append(owner)

    def unlock_player_input(self, owner: str) -> None:
        self.locks.remove(owner)

    def emit_signal(self, event_type: str, **_payload) -> None:
        self.signals.append(event_type)

    def console_log(self, *_args, **_kwargs) -> None:
        pass


@pytest.fixture(autouse=True)
def _arcade(monkeypatch: pytest.MonkeyPatch) -> None:
    import engine.scene_controller_core as core

    monkeypatch.setattr(core.optional_arcade, "arcade", SimpleNamespace(check_for_collision_with_list=_overlap))


def _run(player: SequencePlayer, seconds: float) -> float:
    """Update at 60 fps until the sequence ends (or ``seconds`` pass); the time it took."""
    for frame in range(int(seconds * 60)):
        player.update(1 / 60)
        if not player._active:
            return frame / 60
    return seconds


def test_move_to_past_the_room_edge_and_behind_a_wall_end_and_the_lock_is_released() -> None:
    wall = _Sprite(400.0, 100.0, 32.0, 200.0)  # x 384..416, y 0..200
    window = _Window([wall])
    guide = _Sprite(600.0, 100.0)
    player = SequencePlayer(guide, window, lock_player_input=True, auto_start=True, steps=[
        {"type": "move_to", "x": 900, "speed": 120},  # past the right edge (x 768)
        {"type": "signal", "event": "edge_done"},
        {"type": "move_to", "x": 200, "speed": 120},  # behind the wall
        {"type": "signal", "event": "wall_done"},
    ])
    player.update(1 / 60)  # (auto start: locks the player)
    assert window.locks, "precondition: the sequence locks the player"
    took = _run(player, 30.0)
    assert not player._active, f"the sequence never finished: guide at x={guide.center_x}"
    assert window.signals == ["edge_done", "wall_done"], "each blocked move_to ended and the sequence went on"
    assert window.locks == [], "the player's input lock was released"
    assert guide.left == pytest.approx(wall.right), "it stopped flush against the wall, where it was blocked"
    assert took < 2 * (168 / 120 + 384 / 120 + 2 * BLOCKED_S), "and not long after it was blocked"


def test_a_normal_move_to_still_reaches_its_target_exactly() -> None:
    window = _Window([])
    guide = _Sprite(100.0, 100.0)
    player = SequencePlayer(guide, window, lock_player_input=False, auto_start=True, steps=[
        {"type": "move_to", "x": 700, "y": 300, "speed": 120},
        {"type": "signal", "event": "arrived"},
    ])
    _run(player, 30.0)
    assert (guide.center_x, guide.center_y) == (700.0, 300.0) and window.signals == ["arrived"]


def test_sliding_along_a_wall_at_a_shallow_angle_is_not_blocked() -> None:
    """It gets under 1% of a step nearer each frame while sliding (under ~5.7 degrees), yet it is moving: it arrives.
    (Headway counted as nearness ended it at (124, 106.08), 2 px short of clearing the wall: #770 review.)"""
    window = _Window([_Sprite(150.0, 46.0, 20.0, 92.0)])  # x 140..160, y 0..92
    guide = _Sprite(100.0, 100.0)
    player = SequencePlayer(guide, window, lock_player_input=False, auto_start=True, steps=[
        {"type": "move_to", "x": 200, "y": 109, "speed": 120},
        {"type": "signal", "event": "arrived"},
    ])
    _run(player, 30.0)
    assert (guide.center_x, guide.center_y) == (200.0, 109.0) and window.signals == ["arrived"]


def test_a_slow_mover_is_not_taken_for_a_blocked_one() -> None:
    window = _Window([])
    guide = _Sprite(100.0, 100.0)
    player = SequencePlayer(guide, window, lock_player_input=False, auto_start=True, steps=[
        {"type": "move_to", "x": 110, "speed": 1},  # 10 px at 1 px/s
    ])
    took = _run(player, 30.0)
    assert guide.center_x == 110.0 and took > 7.5, "8 s: it walks until within the 2 px tolerance, then snaps"
