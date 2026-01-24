import json
from pathlib import Path

import mesh_cli


def test_cli_scene_create_is_idempotent(tmp_path: Path) -> None:
    scene_path = tmp_path / "example_scene.json"

    args = [
        "scene",
        "create",
        str(scene_path),
        "--width",
        "4",
        "--height",
        "3",
        "--tile-w",
        "16",
        "--tile-h",
        "16",
        "--layer",
        "Ground:-100",
        "--layer",
        "Deco:-50:0.9",
        "--collision-layer",
        "Ground",
        "--bg",
        "Sky:assets/bg/sky.png:-1000:0.2:1:0",
        "--spawn",
        "default:32:48",
    ]

    rc = mesh_cli.main(args)
    assert rc == 0

    payload = json.loads(scene_path.read_text(encoding="utf-8"))
    tilemap = payload["tilemap"]
    assert tilemap["width"] == 4
    assert tilemap["height"] == 3
    assert tilemap["tilewidth"] == 16
    assert tilemap["tileheight"] == 16
    assert tilemap["collision_layer_id"] == "Ground"
    assert [layer["id"] for layer in tilemap["tile_layers"]] == ["Ground", "Deco"]
    assert len(tilemap["tile_layers"][0]["tiles"]) == 12
    assert len(tilemap["tile_layers"][1]["tiles"]) == 12

    assert payload["background_layers"][0]["id"] == "Sky"
    assert payload["background_layers"][0]["repeat_x"] is True
    assert payload["background_layers"][0]["repeat_y"] is False

    spawn = next(e for e in payload["entities"] if e.get("tag") == "spawn_point")
    assert spawn["spawn_id"] == "default"
    assert spawn["x"] == 32.0
    assert spawn["y"] == 48.0

    before = scene_path.read_text(encoding="utf-8")
    rc2 = mesh_cli.main(args)
    assert rc2 == 0
    after = scene_path.read_text(encoding="utf-8")
    assert after == before

