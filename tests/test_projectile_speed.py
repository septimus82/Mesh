"""A projectile moves at its speed in pixels per second.

Found by the capability lab (docs/reviews/milestone7_capability_lab.md): the speed was used as the
per-frame step, so shots crossed 300 px a frame, passed through targets and walls, and never hit.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine.behaviours.projectile import Projectile

pytestmark = [pytest.mark.fast]


def test_one_second_of_frames_covers_the_speed() -> None:
    sprite = SimpleNamespace(center_x=0.0, center_y=0.0, change_x=0.0, change_y=0.0, angle=0.0)
    Projectile(sprite, SimpleNamespace(), speed=300.0, direction=0.0)
    for _ in range(60):  # the scene's movement stage: arcade's Sprite.update() adds change_x/y once a frame
        sprite.center_x += sprite.change_x
        sprite.center_y += sprite.change_y
    assert sprite.center_x == pytest.approx(300.0)
    assert sprite.center_y == pytest.approx(0.0, abs=1e-6)
