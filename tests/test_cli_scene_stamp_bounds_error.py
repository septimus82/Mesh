import json
from pathlib import Path

import mesh_cli


def test_cli_scene_stamp_errors_on_missing_layer(tmp_path: Path):
    map_path = tmp_path / "map.json"
    map_path.write_text(json.dumps({"width": 8, "height": 8, "tilewidth": 16, "tileheight": 16}), encoding="utf-8")

    scene_path = tmp_path / "scene.json"
    scene_path.write_text(
        json.dumps(
            {
                "tilemap": {"path": str(map_path), "tile_layers": [{"id": "Ground", "z": -100, "parallax": 1.0, "tiles": [0] * 64}]},
                "entities": [],
            }
        ),
        encoding="utf-8",
    )

    stamp_path = tmp_path / "stamp.json"
    stamp_path.write_text(
        json.dumps(
            {
                "id": "basic_room_10x8",
                "width": 2,
                "height": 2,
                "tiles": [{"layer_id": "Walls", "x": 0, "y": 0, "w": 1, "h": 1, "tile": 9}],
            }
        ),
        encoding="utf-8",
    )

    rc = mesh_cli.main(["scene", "stamp", str(scene_path), "--stamp", str(stamp_path), "--x", "0", "--y", "0"])
    assert rc == 1


def test_cli_scene_stamp_errors_on_out_of_bounds_rect(tmp_path: Path):
    map_path = tmp_path / "map.json"
    map_path.write_text(json.dumps({"width": 4, "height": 4, "tilewidth": 16, "tileheight": 16}), encoding="utf-8")

    scene_path = tmp_path / "scene.json"
    scene_path.write_text(
        json.dumps(
            {
                "tilemap": {"path": str(map_path), "tile_layers": [{"id": "Ground", "z": -100, "parallax": 1.0, "tiles": [0] * 16}]},
                "entities": [],
            }
        ),
        encoding="utf-8",
    )

    stamp_path = tmp_path / "stamp.json"
    stamp_path.write_text(
        json.dumps(
            {
                "id": "basic_room_10x8",
                "width": 3,
                "height": 3,
                "tiles": [{"layer_id": "Ground", "x": 0, "y": 0, "w": 3, "h": 3, "tile": 5}],
            }
        ),
        encoding="utf-8",
    )

    # origin places the 3x3 rect beyond the 4x4 map.
    rc = mesh_cli.main(["scene", "stamp", str(scene_path), "--stamp", str(stamp_path), "--x", "3", "--y", "3"])
    assert rc == 1

