import json
from pathlib import Path

import mesh_cli


def test_cli_scene_tilemap_clear_rect_sets_tiles_to_zero(tmp_path: Path):
    map_path = tmp_path / "map.json"
    map_path.write_text(json.dumps({"width": 3, "height": 2}), encoding="utf-8")

    scene_path = tmp_path / "scene.json"
    scene_path.write_text(
        json.dumps(
            {
                "tilemap": {
                    "path": str(map_path),
                    "tile_layers": [{"id": "Ground", "z": -100, "parallax": 1.0, "tiles": [9] * 6}],
                },
                "entities": [],
            }
        ),
        encoding="utf-8",
    )

    rc = mesh_cli.main(
        [
            "scene",
            "tilemap",
            "clear-rect",
            str(scene_path),
            "--layer-id",
            "Ground",
            "--x0",
            "1",
            "--y0",
            "0",
            "--x1",
            "2",
            "--y1",
            "0",
        ]
    )
    assert rc == 0
    payload = json.loads(scene_path.read_text(encoding="utf-8"))
    tiles = payload["tilemap"]["tile_layers"][0]["tiles"]
    assert tiles[0:3] == [9, 0, 0]


def test_cli_scene_tilemap_paint_initializes_tiles_if_missing(tmp_path: Path):
    map_path = tmp_path / "map.json"
    map_path.write_text(json.dumps({"width": 2, "height": 2}), encoding="utf-8")

    scene_path = tmp_path / "scene.json"
    scene_path.write_text(
        json.dumps(
            {
                "tilemap": {
                    "path": str(map_path),
                    "width": 2,
                    "height": 2,
                    "tile_layers": [{"id": "Ground", "z": -100, "parallax": 1.0}],
                },
                "entities": [],
            }
        ),
        encoding="utf-8",
    )

    rc = mesh_cli.main(
        [
            "scene",
            "tilemap",
            "paint",
            str(scene_path),
            "--layer-id",
            "Ground",
            "--x",
            "1",
            "--y",
            "1",
            "--tile",
            "7",
        ]
    )
    assert rc == 0
    payload = json.loads(scene_path.read_text(encoding="utf-8"))
    tiles = payload["tilemap"]["tile_layers"][0]["tiles"]
    assert tiles == [0, 0, 0, 7]
