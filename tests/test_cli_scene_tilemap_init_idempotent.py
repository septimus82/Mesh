import json
from pathlib import Path

import mesh_cli


def test_cli_scene_tilemap_init_creates_layers_and_is_idempotent(tmp_path: Path):
    scene_path = tmp_path / "scene.json"
    scene_path.write_text(json.dumps({"entities": []}), encoding="utf-8")

    rc = mesh_cli.main(
        [
            "scene",
            "tilemap",
            "init",
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
            "--fill",
            "Ground:5",
        ]
    )
    assert rc == 0
    payload = json.loads(scene_path.read_text(encoding="utf-8"))
    tilemap = payload["tilemap"]
    assert tilemap["width"] == 4
    assert tilemap["height"] == 3
    assert tilemap["tilewidth"] == 16
    assert tilemap["tileheight"] == 16
    assert tilemap["collision_layer_id"] == "Ground"

    layers = tilemap["tile_layers"]
    assert [layer["id"] for layer in layers] == ["Ground", "Deco"]
    ground = next(layer for layer in layers if layer["id"] == "Ground")
    deco = next(layer for layer in layers if layer["id"] == "Deco")
    assert len(ground["tiles"]) == 12
    assert len(deco["tiles"]) == 12
    assert all(v == 5 for v in ground["tiles"])
    assert all(v == 0 for v in deco["tiles"])

    before = scene_path.read_text(encoding="utf-8")
    rc2 = mesh_cli.main(
        [
            "scene",
            "tilemap",
            "init",
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
            "--fill",
            "Ground:5",
        ]
    )
    assert rc2 == 0
    after = scene_path.read_text(encoding="utf-8")
    assert after == before

