import json
from pathlib import Path

import mesh_cli


def test_cli_scene_tilemap_fill_rect_idempotent(tmp_path: Path):
    map_path = tmp_path / "map.json"
    map_path.write_text(json.dumps({"width": 4, "height": 3}), encoding="utf-8")

    scene_path = tmp_path / "scene.json"
    scene_path.write_text(
        json.dumps(
            {
                "tilemap": {
                    "path": str(map_path),
                    "tile_layers": [{"id": "Ground", "z": -100, "parallax": 1.0, "tiles": [0] * 12}],
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
            "fill-rect",
            str(scene_path),
            "--layer-id",
            "Ground",
            "--x0",
            "0",
            "--y0",
            "0",
            "--x1",
            "1",
            "--y1",
            "1",
            "--tile",
            "5",
        ]
    )
    assert rc == 0
    payload = json.loads(scene_path.read_text(encoding="utf-8"))
    tiles = payload["tilemap"]["tile_layers"][0]["tiles"]
    assert tiles[0:2] == [5, 5]
    assert tiles[4:6] == [5, 5]

    before_text = scene_path.read_text(encoding="utf-8")
    rc2 = mesh_cli.main(
        [
            "scene",
            "tilemap",
            "fill-rect",
            str(scene_path),
            "--layer-id",
            "Ground",
            "--x0",
            "0",
            "--y0",
            "0",
            "--x1",
            "1",
            "--y1",
            "1",
            "--tile",
            "5",
        ]
    )
    assert rc2 == 0
    after_text = scene_path.read_text(encoding="utf-8")
    assert after_text == before_text

