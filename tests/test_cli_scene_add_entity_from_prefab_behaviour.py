import json
from pathlib import Path

import mesh_cli


def test_cli_scene_add_entity_from_prefab_behaviour_config(tmp_path: Path):
    scene_path = tmp_path / "scene.json"
    scene_path.write_text(json.dumps({"entities": []}), encoding="utf-8")

    rc = mesh_cli.main(
        [
            "scene",
            "add-entity",
            str(scene_path),
            "--prefab-id",
            "slime_blob",
            "--x",
            "1",
            "--y",
            "2",
            "--behaviour",
            "AutoAnimationByMovement",
            "--behaviour-json",
            'AutoAnimationByMovement={"idle":"idle","walk":"walk","speed_threshold":0.1,"prefer":["walk","idle"]}',
        ]
    )
    assert rc == 0

    payload = json.loads(scene_path.read_text(encoding="utf-8"))
    ent = payload["entities"][0]
    assert any(b.get("type") == "AutoAnimationByMovement" for b in ent.get("behaviours", []) if isinstance(b, dict))
    cfg = ent.get("behaviour_config", {})
    assert isinstance(cfg, dict)
    assert cfg["AutoAnimationByMovement"]["speed_threshold"] == 0.1
    assert cfg["AutoAnimationByMovement"]["idle"] == "idle"

