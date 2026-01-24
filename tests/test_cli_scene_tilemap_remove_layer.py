import json
from pathlib import Path

import mesh_cli


def test_cli_scene_tilemap_remove_layer_removes_and_clears_collision(tmp_path: Path):
    map_path = tmp_path / "map.json"
    map_path.write_text(json.dumps({"width": 2, "height": 2}), encoding="utf-8")

    scene_path = tmp_path / "scene.json"
    scene_path.write_text(
        json.dumps(
            {
                "tilemap": {
                    "path": str(map_path),
                    "collision_layer_id": "B",
                    "tile_layers": [
                        {"id": "A", "z": -100, "parallax": 1.0},
                        {"id": "B", "z": 0, "parallax": 1.0},
                    ],
                },
                "entities": [],
            }
        ),
        encoding="utf-8",
    )

    rc = mesh_cli.main(["scene", "tilemap", "remove-layer", str(scene_path), "--id", "B"])
    assert rc == 0
    payload = json.loads(scene_path.read_text(encoding="utf-8"))
    assert [entry["id"] for entry in payload["tilemap"]["tile_layers"]] == ["A"]
    assert "collision_layer_id" not in payload["tilemap"]


def test_cli_scene_tilemap_remove_layer_noop_when_absent(tmp_path: Path):
    map_path = tmp_path / "map.json"
    map_path.write_text(json.dumps({"width": 2, "height": 2}), encoding="utf-8")

    scene_path = tmp_path / "scene.json"
    scene_path.write_text(
        json.dumps({"tilemap": {"path": str(map_path), "tile_layers": [{"id": "A", "z": -100, "parallax": 1.0}]}}),
        encoding="utf-8",
    )

    rc = mesh_cli.main(["scene", "tilemap", "remove-layer", str(scene_path), "--id", "Missing"])
    assert rc == 0
    payload = json.loads(scene_path.read_text(encoding="utf-8"))
    assert [entry["id"] for entry in payload["tilemap"]["tile_layers"]] == ["A"]
