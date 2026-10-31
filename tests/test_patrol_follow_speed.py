"""Patrol and FollowTarget move at their speed in pixels per second.

The capability lab found SequencePlayer handing the scene's mover a speed (px/s) plus dt, which the
mover reads as this frame's distance and ignores dt. Patrol and FollowTarget called it the same way,
so they moved `speed` px every frame.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine.behaviours.follow import FollowBehaviour
from engine.behaviours.patrol import PatrolBehaviour

pytestmark = [pytest.mark.fast]


class _Window:
    def __init__(self, target=None) -> None:
        self.target = target

    def move_entity_with_collision(self, sprite, dx: float, dy: float, friction: float = 1.0) -> None:  # noqa: ARG002
        sprite.center_x += dx
        sprite.center_y += dy

    def find_sprite_by_name(self, _name):
        return self.target


def _sprite(x: float, y: float) -> SimpleNamespace:
    return SimpleNamespace(center_x=x, center_y=y, mesh_entity_data={}, mesh_name="mover")


def test_patrol_covers_its_speed_per_second() -> None:
    sprite = _sprite(0.0, 0.0)
    patrol = PatrolBehaviour(sprite, _Window(), patrol_points=[{"x": 0, "y": 0}, {"x": 1000, "y": 0}], patrol_speed=80.0)
    for _ in range(60):
        patrol.update(1 / 60)
    assert 70.0 <= sprite.center_x <= 90.0


def test_follow_target_covers_its_speed_per_second() -> None:
    target = _sprite(1000.0, 0.0)
    sprite = _sprite(0.0, 0.0)
    follow = FollowBehaviour(sprite, _Window(target), follow_target="leader", follow_speed=100.0)
    for _ in range(60):
        follow.update(1 / 60)
    assert 90.0 <= sprite.center_x <= 110.0
