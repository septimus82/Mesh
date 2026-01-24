import json
from pathlib import Path

import mesh_cli


def test_cli_scene_tilemap_brush_clips_with_flag(tmp_path: Path):
    scene_path = tmp_path / "scene.json"
    scene_path.write_text(
        json.dumps(
            {
                "tilemap": {"width": 2, "height": 2, "tile_layers": [{"id": "Ground", "z": -100, "tiles": [0] * 4}]},
                "entities": [],
            }
        ),
        encoding="utf-8",
    )

    brush_path = tmp_path / "brush.json"
    brush_path.write_text(json.dumps({"id": "b", "w": 2, "h": 2, "tiles": [[1, 2], [3, 4]]}), encoding="utf-8")

    rc = mesh_cli.main(
        [
            "scene",
            "tilemap",
            "brush",
            str(scene_path),
            "--layer-id",
            "Ground",
            "--brush",
            str(brush_path),
            "--x",
            "1",
            "--y",
            "1",
            "--clip",
        ]
    )
    assert rc == 0

    payload = json.loads(scene_path.read_text(encoding="utf-8"))
    tiles = payload["tilemap"]["tile_layers"][0]["tiles"]
    assert tiles == [0, 0, 0, 1]
