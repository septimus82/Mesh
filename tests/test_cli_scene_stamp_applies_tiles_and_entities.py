import json
from pathlib import Path

import mesh_cli


def test_cli_scene_stamp_applies_tiles_and_entities(tmp_path: Path):
    map_path = tmp_path / "map.json"
    map_w, map_h = 64, 64
    map_path.write_text(
        json.dumps({"width": map_w, "height": map_h, "tilewidth": 16, "tileheight": 16}),
        encoding="utf-8",
    )

    scene_path = tmp_path / "scene.json"
    scene_path.write_text(
        json.dumps(
            {
                "tilemap": {
                    "path": str(map_path),
                    "tile_layers": [
                        {"id": "Ground", "z": -100, "parallax": 1.0, "tiles": [0] * (map_w * map_h)},
                        {"id": "Walls", "z": -50, "parallax": 1.0, "tiles": [0] * (map_w * map_h)},
                    ],
                },
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
                "width": 10,
                "height": 8,
                "tiles": [
                    {"layer_id": "Ground", "x": 0, "y": 0, "w": 10, "h": 8, "tile": 5},
                    {"layer_id": "Walls", "x": 0, "y": 0, "w": 10, "h": 1, "tile": 9},
                ],
                "entities": [{"prefab_id": "torch_wisp", "x": 2, "y": 2, "id_suffix": "torch1"}],
            }
        ),
        encoding="utf-8",
    )

    origin_x, origin_y = 10, 20
    rc = mesh_cli.main(
        [
            "scene",
            "stamp",
            str(scene_path),
            "--stamp",
            str(stamp_path),
            "--x",
            str(origin_x),
            "--y",
            str(origin_y),
            "--id-prefix",
            "demo",
        ]
    )
    assert rc == 0

    payload = json.loads(scene_path.read_text(encoding="utf-8"))
    ground = next(layer for layer in payload["tilemap"]["tile_layers"] if layer["id"] == "Ground")["tiles"]
    walls = next(layer for layer in payload["tilemap"]["tile_layers"] if layer["id"] == "Walls")["tiles"]

    def idx(x: int, y: int) -> int:
        return y * map_w + x

    assert ground[idx(10, 20)] == 5
    assert ground[idx(19, 27)] == 5
    assert walls[idx(10, 20)] == 9
    assert walls[idx(19, 20)] == 9
    assert walls[idx(10, 21)] == 0

    expected_entity_id = "scene_demo_torch1_10_20_0_0"
    ent = next(e for e in payload["entities"] if e.get("id") == expected_entity_id)
    assert ent["prefab_id"] == "torch_wisp"
    assert ent["x"] == (origin_x + 2 + 0.5) * 16
    assert ent["y"] == (origin_y + 2 + 0.5) * 16

    before = scene_path.read_text(encoding="utf-8")
    rc2 = mesh_cli.main(
        [
            "scene",
            "stamp",
            str(scene_path),
            "--stamp",
            str(stamp_path),
            "--x",
            str(origin_x),
            "--y",
            str(origin_y),
            "--id-prefix",
            "demo",
        ]
    )
    assert rc2 == 0
    after = scene_path.read_text(encoding="utf-8")
    assert after == before

