import json
from pathlib import Path

import mesh_cli


def test_cli_scene_tilemap_resize_idempotent(tmp_path: Path):
    scene_path = tmp_path / "scene.json"
    scene_path.write_text(
        json.dumps(
            {
                "tilemap": {
                    "width": 2,
                    "height": 2,
                    "tilewidth": 16,
                    "tileheight": 16,
                    "tile_layers": [{"id": "Ground", "z": -100, "tiles": [1, 2, 3, 4]}],
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
            "resize",
            str(scene_path),
            "--width",
            "3",
            "--height",
            "3",
            "--anchor",
            "tl",
            "--fill-tile",
            "9",
        ]
    )
    assert rc == 0
    payload = json.loads(scene_path.read_text(encoding="utf-8"))
    assert payload["tilemap"]["width"] == 3
    assert payload["tilemap"]["height"] == 3
    tiles = payload["tilemap"]["tile_layers"][0]["tiles"]
    assert tiles == [1, 2, 9, 3, 4, 9, 9, 9, 9]

    before = scene_path.read_text(encoding="utf-8")
    rc2 = mesh_cli.main(
        [
            "scene",
            "tilemap",
            "resize",
            str(scene_path),
            "--width",
            "3",
            "--height",
            "3",
            "--anchor",
            "tl",
            "--fill-tile",
            "9",
        ]
    )
    assert rc2 == 0
    after = scene_path.read_text(encoding="utf-8")
    assert after == before

