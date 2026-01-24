import pytest
from engine.palette_mode import _apply_brush

def test_apply_brush_mutates():
    scene = {
        "tilemap": {
            "width": 10, "height": 10,
            "tile_layers": [{"id": "ground", "tiles": [0]*100}]
        }
    }
    brush = {
        "id": "test_brush",
        "w": 2, "h": 2,
        "tiles": [[1, 1], [1, 1]]
    }
    
    _apply_brush(scene, brush, 0, 0, "ground")
    
    tiles = scene["tilemap"]["tile_layers"][0]["tiles"]
    assert tiles[0] == 1
    assert tiles[1] == 1
    assert tiles[10] == 1
    assert tiles[11] == 1
