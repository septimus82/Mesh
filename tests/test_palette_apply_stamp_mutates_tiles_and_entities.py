from engine.palette_mode import _apply_stamp


def test_apply_stamp_mutates():
    scene = {
        "tilemap": {
            "width": 10, "height": 10,
            "tile_layers": [{"id": "ground", "tiles": [0]*100}]
        },
        "entities": []
    }
    stamp = {
        "id": "test_stamp",
        "width": 2, "height": 2,
        "tiles": [
            {"layer_id": "ground", "x": 0, "y": 0, "w": 2, "h": 2, "tile": 1}
        ],
        "entities": [{"prefab_id": "player", "x": 0, "y": 0, "id_suffix": "1"}]
    }

    _apply_stamp(scene, stamp, 0, 0)

    # Check tiles
    tiles = scene["tilemap"]["tile_layers"][0]["tiles"]
    assert tiles[0] == 1
    assert tiles[1] == 1
    assert tiles[10] == 1
    assert tiles[11] == 1
    assert tiles[2] == 0

    # Check entities
    assert len(scene["entities"]) == 1
    assert scene["entities"][0]["prefab_id"] == "player"
