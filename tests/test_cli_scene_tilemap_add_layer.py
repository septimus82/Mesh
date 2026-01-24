import json
from pathlib import Path

import mesh_cli


def test_cli_scene_tilemap_add_layer_idempotent_and_updates(tmp_path: Path):
    map_path = tmp_path / "map.json"
    map_path.write_text(json.dumps({"width": 2, "height": 2}), encoding="utf-8")

    scene_path = tmp_path / "scene.json"
    scene_path.write_text(
        json.dumps(
            {
                "tilemap": {
                    "path": str(map_path),
                    "layers": [{"name": "Ground", "z": "background"}],
                },
                "entities": [],
            }
        ),
        encoding="utf-8",
    )

    rc = mesh_cli.main(
        ["scene", "tilemap", "add-layer", str(scene_path), "--id", "Clouds", "--z", "-200", "--parallax", "0.5"]
    )
    assert rc == 0
    payload = json.loads(scene_path.read_text(encoding="utf-8"))
    assert payload["tilemap"]["path"] == str(map_path)
    assert isinstance(payload["tilemap"]["tile_layers"], list)
    assert [entry["id"] for entry in payload["tilemap"]["tile_layers"] if isinstance(entry, dict)] == [
        "Ground",
        "Clouds",
    ]

    rc2 = mesh_cli.main(
        ["scene", "tilemap", "add-layer", str(scene_path), "--id", "Clouds", "--z", "-200", "--parallax", "0.5"]
    )
    assert rc2 == 0
    payload2 = json.loads(scene_path.read_text(encoding="utf-8"))
    assert [entry["id"] for entry in payload2["tilemap"]["tile_layers"] if isinstance(entry, dict)] == [
        "Ground",
        "Clouds",
    ]

    rc3 = mesh_cli.main(
        ["scene", "tilemap", "add-layer", str(scene_path), "--id", "Clouds", "--z", "-150", "--parallax", "0.75"]
    )
    assert rc3 == 0
    payload3 = json.loads(scene_path.read_text(encoding="utf-8"))
    clouds = next(entry for entry in payload3["tilemap"]["tile_layers"] if entry.get("id") == "Clouds")
    assert clouds["z"] == -150
    assert clouds["parallax"] == 0.75


def test_cli_scene_tilemap_add_layer_collision_sets_collision_layer_id(tmp_path: Path):
    map_path = tmp_path / "map.json"
    map_path.write_text(json.dumps({"width": 2, "height": 2}), encoding="utf-8")

    scene_path = tmp_path / "scene.json"
    scene_path.write_text(json.dumps({"tilemap": {"path": str(map_path)}, "entities": []}), encoding="utf-8")

    rc = mesh_cli.main(["scene", "tilemap", "add-layer", str(scene_path), "--id", "Ground", "--z", "-100", "--collision"])
    assert rc == 0
    payload = json.loads(scene_path.read_text(encoding="utf-8"))
    assert payload["tilemap"]["collision_layer_id"] == "Ground"

