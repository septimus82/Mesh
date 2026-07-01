from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from engine.assets import AssetManager

pytestmark = pytest.mark.fast


def test_load_sprite_sheet_slices_arcade3_texture_grid(tmp_path: Path) -> None:
    sheet_path = tmp_path / "walk.png"
    image = Image.new("RGBA", (384, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for index in range(6):
        x = index * 64 + 20
        draw.rectangle((x, 8, x + 20, 56), fill=(20 * index, 120, 240, 255))
    image.save(sheet_path)

    textures = AssetManager().load_sprite_sheet(str(sheet_path), 64, 64, 6)

    assert len(textures) == 6
    assert all(getattr(texture, "width", 0) == 64 for texture in textures)
    assert all(getattr(texture, "height", 0) == 64 for texture in textures)
    assert all(texture.image.getbbox() is not None for texture in textures)
