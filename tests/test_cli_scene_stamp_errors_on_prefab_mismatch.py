import json
from pathlib import Path

import mesh_cli


def test_cli_scene_stamp_errors_on_prefab_mismatch(tmp_path: Path):
    map_path = tmp_path / "map.json"
    map_path.write_text(json.dumps({"width": 8, "height": 8, "tilewidth": 16, "tileheight": 16}), encoding="utf-8")

    scene_path = tmp_path / "scene.json"
    scene_path.write_text(
        json.dumps(
            {
                "tilemap": {
                    "path": str(map_path),
                    "tile_layers": [{"id": "Ground", "z": -100, "parallax": 1.0, "tiles": [0] * 64}],
                },
                "entities": [
                    {
                        "id": "scene_demo_torch1_1_1_0_0",
                        "prefab_id": "slime_blob",
                        "x": 0,
                        "y": 0,
                    }
                ],
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
                "tiles": [],
                "entities": [{"prefab_id": "torch_wisp", "x": 0, "y": 0, "id_suffix": "torch1"}],
            }
        ),
        encoding="utf-8",
    )

    rc = mesh_cli.main(
        [
            "scene",
            "stamp",
            str(scene_path),
            "--stamp",
            str(stamp_path),
            "--x",
            "1",
            "--y",
            "1",
            "--id-prefix",
            "demo",
        ]
    )
    assert rc == 1

