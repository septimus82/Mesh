import json
from pathlib import Path

import mesh_cli


def test_cli_scene_tilemap_flood_fill_max_tiles_clip_writes_partial_deterministically(tmp_path: Path):
    scene_path = tmp_path / "scene.json"
    w, h = 4, 4
    scene_path.write_text(
        json.dumps(
            {
                "tilemap": {
                    "width": w,
                    "height": h,
                    "tilewidth": 16,
                    "tileheight": 16,
                    "tile_layers": [{"id": "Ground", "z": -100, "tiles": [0] * (w * h)}],
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
            "flood-fill",
            str(scene_path),
            "--layer-id",
            "Ground",
            "--x",
            "0",
            "--y",
            "0",
            "--tile",
            "1",
            "--max-tiles",
            "5",
            "--clip",
        ]
    )
    assert rc == 0

    payload = json.loads(scene_path.read_text(encoding="utf-8"))
    tiles = payload["tilemap"]["tile_layers"][0]["tiles"]
    expected = [0] * (w * h)
    for idx in [0, 1, 4, 2, 5]:
        expected[idx] = 1
    assert tiles == expected

