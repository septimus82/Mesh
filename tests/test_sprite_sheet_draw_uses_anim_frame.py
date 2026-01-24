from __future__ import annotations

import arcade
from PIL import Image

from engine.animation import AnimationFactory


class DummyAssets:
    def __init__(self, texture: arcade.Texture):
        self._texture = texture

    def get_texture(self, path: str):
        if path == "sheet.png":
            return self._texture
        return None


def test_sprite_sheet_draw_uses_anim_frame_after_updates():
    sheet = Image.new("RGBA", (32, 16), (0, 0, 0, 0))
    for x in range(0, 16):
        for y in range(0, 16):
            sheet.putpixel((x, y), (255, 0, 0, 255))
    for x in range(16, 32):
        for y in range(0, 16):
            sheet.putpixel((x, y), (0, 255, 0, 255))

    base_texture = arcade.Texture(name="sheet", image=sheet)
    factory = AnimationFactory(DummyAssets(base_texture))  # type: ignore[arg-type]

    sprite = arcade.Sprite()
    entity = {
        "name": "Test",
        "sprite": "sheet.png",
        "sprite_sheet": {"frame_width": 16, "frame_height": 16, "margin": 0, "spacing": 0},
        "animations": {"idle": {"frames": [0, 1], "fps": 10.0, "loop": True}},
        "default_animation": "idle",
    }

    player = factory.build_for_entity(sprite, entity, debug=False)
    assert player is not None

    assert sprite.texture is not None
    assert sprite.texture.image.getpixel((8, 8))[:3] == (255, 0, 0)

    player.update(0.10)
    assert sprite.texture.image.getpixel((8, 8))[:3] == (0, 255, 0)

    player.update(0.10)
    assert sprite.texture.image.getpixel((8, 8))[:3] == (255, 0, 0)

