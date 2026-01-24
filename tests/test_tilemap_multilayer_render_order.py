import arcade
import pytest

from engine.tilemap import TilemapDrawLayer, sort_tilemap_draw_layers


pytestmark = [pytest.mark.integration, pytest.mark.slow]


def test_tilemap_multilayer_render_order_sorted_by_z_then_id():
    layers = [
        TilemapDrawLayer(id="fg_b", z=0, parallax=1.0, sprites=arcade.SpriteList()),
        TilemapDrawLayer(id="bg_c", z=-10, parallax=1.0, sprites=arcade.SpriteList()),
        TilemapDrawLayer(id="bg_a", z=-10, parallax=1.0, sprites=arcade.SpriteList()),
        TilemapDrawLayer(id="fg_a", z=0, parallax=1.0, sprites=arcade.SpriteList()),
    ]

    ordered = sort_tilemap_draw_layers(layers)
    assert [(layer.z, layer.id) for layer in ordered] == [
        (-10, "bg_a"),
        (-10, "bg_c"),
        (0, "fg_a"),
        (0, "fg_b"),
    ]
