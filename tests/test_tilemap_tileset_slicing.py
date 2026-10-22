"""Tile ids map to the right part of a multi-row tileset image.

Rows used to come out mirrored: the crop used bottom-up y on a top-down image, which
only shows with tilesets of two or more rows.
"""

from __future__ import annotations

import json

import pytest
from PIL import Image

from engine.tilemap import TilemapManager, Tileset

pytestmark = pytest.mark.fast

RED, BLUE, GREEN, WHITE = (255, 0, 0, 255), (0, 0, 255, 255), (0, 255, 0, 255), (255, 255, 255, 255)


def _tileset(tmp_path):
    image = Image.new("RGBA", (64, 64))
    for (x, y), colour in {(0, 0): RED, (32, 0): BLUE, (0, 32): GREEN, (32, 32): WHITE}.items():
        image.paste(colour, (x, y, x + 32, y + 32))
    path = tmp_path / "tiles.png"
    image.save(path)
    return Tileset(name="t", first_gid=1, tile_width=32, tile_height=32, spacing=0, margin=0, columns=2,
                   tile_count=4, image_path=str(path), image_width=64, image_height=64, tile_properties={})


def test_slice_coordinates_are_top_left_row_major(tmp_path) -> None:
    tileset = _tileset(tmp_path)
    assert [tileset.slice_coordinates(i) for i in range(4)] == [(0, 0), (32, 0), (0, 32), (32, 32)]


def test_tile_textures_come_from_the_right_row(tmp_path) -> None:
    tileset = _tileset(tmp_path)
    manager = TilemapManager.__new__(TilemapManager)
    manager._tile_texture_cache = {}
    manager._tileset_images = {}
    for local_id, colour in enumerate((RED, BLUE, GREEN, WHITE)):
        texture = manager._get_tile_texture(tileset, local_id)
        assert texture is not None
        assert texture.image.getpixel((16, 16)) == colour, f"tile {local_id}"


def test_external_json_tileset_image_resolves_next_to_the_tileset(tmp_path) -> None:
    (tmp_path / "tilesets").mkdir()
    Image.new("RGBA", (32, 32), RED).save(tmp_path / "tilesets" / "one.png")
    (tmp_path / "tilesets" / "one.json").write_text(json.dumps({
        "name": "one", "tilewidth": 32, "tileheight": 32, "columns": 1, "tilecount": 1,
        "image": "one.png", "imagewidth": 32, "imageheight": 32}), encoding="utf-8")
    (tmp_path / "maps").mkdir()
    manager = TilemapManager.__new__(TilemapManager)
    tilesets = manager._load_tilesets(tmp_path / "maps", [{"firstgid": 1, "source": "../tilesets/one.json"}])
    assert len(tilesets) == 1
    assert tilesets[0].image_path == str((tmp_path / "tilesets" / "one.png").resolve())


def test_inline_layer_missing_from_the_map_file_still_loads(tmp_path) -> None:
    (tmp_path / "tilesets").mkdir()
    Image.new("RGBA", (32, 32), RED).save(tmp_path / "tilesets" / "one.png")
    (tmp_path / "tilesets" / "one.json").write_text(json.dumps({
        "name": "one", "tilewidth": 32, "tileheight": 32, "columns": 1, "tilecount": 1,
        "image": "one.png", "imagewidth": 32, "imageheight": 32}), encoding="utf-8")
    (tmp_path / "map.json").write_text(json.dumps({
        "orientation": "orthogonal", "width": 2, "height": 1, "tilewidth": 32, "tileheight": 32,
        "tilesets": [{"firstgid": 1, "source": "tilesets/one.json"}],
        "layers": [{"name": "ground", "type": "tilelayer", "width": 2, "height": 1, "data": [1, 1]}]}), encoding="utf-8")
    manager = TilemapManager(assets=None)
    configs = [{"id": "ground", "z": -20}, {"id": "overhead", "z": 10}]
    instance = manager.load_map(str(tmp_path / "map.json"), configs, overrides={"layers": {"overhead": [0, 1]}})
    assert instance is not None
    assert len(instance.layer_lookup["overhead"]) == 1  # drawn from the scene's tiles alone
    assert instance.layer_data["overhead"] == [0, 1]
