from __future__ import annotations

from engine.culling import is_sprite_visible, sprite_bounds


def test_render_queue_culling_counter_math() -> None:
    camera_rect = (0.0, 0.0, 100.0, 100.0)
    sprites = [
        (10.0, 10.0, 10.0, 10.0),
        (50.0, 50.0, 20.0, 20.0),
        (150.0, 50.0, 10.0, 10.0),
        (-30.0, 20.0, 10.0, 10.0),
    ]
    submitted = 0
    culled = 0
    for x, y, w, h in sprites:
        rect = sprite_bounds(x, y, w, h)
        if is_sprite_visible(camera_rect, rect):
            submitted += 1
        else:
            culled += 1
    assert submitted == 2
    assert culled == 2
