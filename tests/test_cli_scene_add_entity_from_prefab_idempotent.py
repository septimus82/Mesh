import json
from pathlib import Path

import mesh_cli


def test_cli_scene_add_entity_from_prefab_idempotent(tmp_path: Path):
    scene_path = tmp_path / "scene.json"
    scene_path.write_text(json.dumps({"entities": []}), encoding="utf-8")

    rc = mesh_cli.main(["scene", "add-entity", str(scene_path), "--prefab-id", "slime_blob", "--x", "10", "--y", "20"])
    assert rc == 0

    payload = json.loads(scene_path.read_text(encoding="utf-8"))
    assert len(payload["entities"]) == 1
    ent = payload["entities"][0]
    assert ent["prefab_id"] == "slime_blob"
    assert ent["x"] == 10.0
    assert ent["y"] == 20.0
    assert ent["id"] == "scene_slime_blob_10_20_0_0"

    rc2 = mesh_cli.main(["scene", "add-entity", str(scene_path), "--prefab-id", "slime_blob", "--x", "10", "--y", "20"])
    assert rc2 == 0
    payload2 = json.loads(scene_path.read_text(encoding="utf-8"))
    assert len(payload2["entities"]) == 1

    rc3 = mesh_cli.main(
        [
            "scene",
            "add-entity",
            str(scene_path),
            "--prefab-id",
            "slime_blob",
            "--x",
            "10",
            "--y",
            "20",
            "--name",
            "MySlime",
        ]
    )
    assert rc3 == 0
    payload3 = json.loads(scene_path.read_text(encoding="utf-8"))
    assert len(payload3["entities"]) == 1
    assert payload3["entities"][0]["mesh_name"] == "MySlime"

