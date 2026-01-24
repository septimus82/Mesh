import json
from pathlib import Path

import mesh_cli


def test_cli_scene_backgrounds_add_update_remove_idempotent(tmp_path: Path):
    scene_path = tmp_path / "scene.json"
    scene_path.write_text(json.dumps({"name": "tmp", "entities": []}), encoding="utf-8")

    rc = mesh_cli.main(
        [
            "scene",
            "backgrounds",
            "add-layer",
            str(scene_path),
            "--id",
            "Sky",
            "--path",
            "assets/bg/sky.png",
            "--z",
            "-1000",
            "--parallax",
            "0.25",
            "--repeat-x",
        ]
    )
    assert rc == 0
    payload = json.loads(scene_path.read_text(encoding="utf-8"))
    assert payload["background_layers"] == [
        {
            "id": "Sky",
            "path": "assets/bg/sky.png",
            "z": -1000,
            "parallax": 0.25,
            "repeat_x": True,
            "repeat_y": False,
        }
    ]

    rc2 = mesh_cli.main(
        [
            "scene",
            "backgrounds",
            "add-layer",
            str(scene_path),
            "--id",
            "Sky",
            "--path",
            "assets/bg/sky.png",
            "--z",
            "-1000",
            "--parallax",
            "0.25",
            "--repeat-x",
        ]
    )
    assert rc2 == 0
    payload2 = json.loads(scene_path.read_text(encoding="utf-8"))
    assert payload2["background_layers"] == payload["background_layers"]

    rc3 = mesh_cli.main(
        [
            "scene",
            "backgrounds",
            "add-layer",
            str(scene_path),
            "--id",
            "Sky",
            "--path",
            "assets/bg/sky.png",
            "--z",
            "-900",
            "--parallax",
            "0.25",
            "--repeat-x",
        ]
    )
    assert rc3 == 0
    payload3 = json.loads(scene_path.read_text(encoding="utf-8"))
    assert payload3["background_layers"][0]["z"] == -900

    rc4 = mesh_cli.main(["scene", "backgrounds", "remove-layer", str(scene_path), "--id", "Sky"])
    assert rc4 == 0
    payload4 = json.loads(scene_path.read_text(encoding="utf-8"))
    assert payload4.get("background_layers") == []

    rc5 = mesh_cli.main(["scene", "backgrounds", "remove-layer", str(scene_path), "--id", "Missing"])
    assert rc5 == 0
    payload5 = json.loads(scene_path.read_text(encoding="utf-8"))
    assert payload5.get("background_layers") == []

