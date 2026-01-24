import json
from pathlib import Path

import mesh_cli


def test_cli_scene_tilemap_flood_fill_idempotent(tmp_path: Path):
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
        ]
    )
    assert rc == 0

    before = scene_path.read_text(encoding="utf-8")
    rc2 = mesh_cli.main(
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
        ]
    )
    assert rc2 == 0
    after = scene_path.read_text(encoding="utf-8")
    assert after == before

