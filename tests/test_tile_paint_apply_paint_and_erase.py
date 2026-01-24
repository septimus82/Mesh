from __future__ import annotations


def test_apply_paint_and_erase_changes_tiles() -> None:
    from engine.tile_paint_mode import apply_erase, apply_paint

    scene = {
        "tilemap": {
            "tile_layers": [
                {"id": "Ground", "tiles": [0] * 9},
            ],
        }
    }

    assert apply_paint(scene, layer_id="Ground", tx=1, ty=1, tile_id=5, map_width=3, map_height=3) is True
    assert scene["tilemap"]["tile_layers"][0]["tiles"][4] == 5
    assert apply_paint(scene, layer_id="Ground", tx=1, ty=1, tile_id=5, map_width=3, map_height=3) is False

    assert apply_erase(scene, layer_id="Ground", tx=1, ty=1, map_width=3, map_height=3) is True
    assert scene["tilemap"]["tile_layers"][0]["tiles"][4] == 0

