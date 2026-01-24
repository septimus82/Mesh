from __future__ import annotations

from engine.culling import is_sprite_visible, sprite_bounds


def test_culling_sprite_bounds_visibility() -> None:
    camera_rect = (0.0, 0.0, 100.0, 100.0)
    visible_rect = sprite_bounds(50.0, 50.0, 10.0, 10.0)
    assert is_sprite_visible(camera_rect, visible_rect) is True

    culled_rect = sprite_bounds(200.0, 50.0, 10.0, 10.0)
    assert is_sprite_visible(camera_rect, culled_rect) is False
    assert is_sprite_visible(camera_rect, culled_rect, margin=120.0) is True
