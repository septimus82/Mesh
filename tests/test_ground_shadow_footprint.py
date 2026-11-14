"""Milestone 14: the shadow under an object fits what touches the ground.

One fixed 24x8 ellipse sat as a speck under a large prop and as a slab under a sign's post. The size comes from the
picture's opaque pixels across its bottom rows; a character keeps the 24x8 it always had, and a sprite is measured
once (a walk cycle doesn't make its shadow pulse).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw

from engine.scene_render_pipeline import _ground_shadow_size

pytestmark = pytest.mark.fast


def _picture(width: int, height: int, feet: tuple[int, int], name: str) -> SimpleNamespace:
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle([2, 2, width - 3, height - 8], fill=(200, 100, 50, 255))  # a body wider than its feet
    draw.rectangle([feet[0], height - 8, feet[1] - 1, height - 1], fill=(40, 40, 40, 255))
    return SimpleNamespace(image=image, atlas_name=name)


def test_a_characters_feet_keep_the_shadow_it_always_had() -> None:
    hero = SimpleNamespace(texture=_picture(32, 48, (10, 22), "hero"), scale_x=1.0)
    assert _ground_shadow_size(hero) == (24.0, 8.0)


def test_a_large_prop_gets_a_shadow_its_size_and_a_post_a_slim_one() -> None:
    big = SimpleNamespace(texture=_picture(64, 64, (12, 52), "boulder"), scale_x=1.5)
    post = SimpleNamespace(texture=_picture(32, 32, (13, 19), "sign"), scale_x=1.0)
    big_w, big_h = _ground_shadow_size(big)
    post_w, _ = _ground_shadow_size(post)
    assert big_w > 80 and big_h == pytest.approx(big_w / 3)
    assert post_w == 15.0, "6 px of post: a slim shadow, not a 24 px slab"


def test_a_sprite_is_measured_once_and_a_picture_without_pixels_keeps_the_default() -> None:
    hero = SimpleNamespace(texture=_picture(32, 48, (10, 22), "walk0"), scale_x=1.0)
    first = _ground_shadow_size(hero)
    hero.texture = _picture(32, 48, (14, 18), "walk1")  # legs together in the next frame
    assert _ground_shadow_size(hero) == first
    empty = SimpleNamespace(texture=SimpleNamespace(image=Image.new("RGBA", (8, 8)), atlas_name="empty"), scale_x=1.0)
    assert _ground_shadow_size(empty) is None
    assert _ground_shadow_size(SimpleNamespace(texture=None)) is None
