"""SequencePlayer's move_to step walks at its speed and stops on the target.

Found by the capability lab (docs/reviews/milestone7_capability_lab.md): the step passed a speed
(px per second) where the move expects this frame's distance, so the object jumped `speed` px a
frame, overshot, swung around the target for ever, and the sequence never got to its next step.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine.behaviours.sequence_player import SequencePlayer

pytestmark = [pytest.mark.fast]


class _Window:
    def move_entity_with_collision(self, sprite, dx: float, dy: float, friction: float = 1.0) -> None:  # noqa: ARG002
        sprite.center_x += dx
        sprite.center_y += dy


def _player(entity) -> SequencePlayer:
    player = object.__new__(SequencePlayer)
    player.entity, player.window = entity, _Window()
    player._step_state, player.move_tolerance, player.default_move_speed = {}, 2.0, 120.0
    return player


def test_move_to_walks_at_its_speed_and_arrives() -> None:
    entity = SimpleNamespace(center_x=272.0, center_y=176.0)
    player = _player(entity)
    step = {"type": "move_to", "x": 96, "y": 0, "relative": True, "speed": 80}
    xs, done, frames = [], False, 0
    while not done and frames < 600:
        done = player._step_move_to(step, 1 / 60)
        xs.append(entity.center_x)
        frames += 1
    assert done, f"never arrived; last x {xs[-5:]}"
    assert entity.center_x == pytest.approx(368.0)
    assert max(xs) <= 368.0 + 1e-6  # never past the target
    assert 1.1 <= frames / 60 <= 1.3  # 96 px at 80 px/s
