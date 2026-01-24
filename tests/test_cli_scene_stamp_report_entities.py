import json
from pathlib import Path

import mesh_cli


def test_cli_scene_stamp_report_entities_add_and_update(tmp_path: Path, capsys):
    scene_path = tmp_path / "scene.json"
    scene_path.write_text(
        json.dumps(
            {
                "tilemap": {"width": 10, "height": 10, "tilewidth": 16, "tileheight": 16, "tile_layers": [{"id": "Ground", "z": -100, "tiles": [0] * 100}]},
                "entities": [],
            }
        ),
        encoding="utf-8",
    )

    stamp_path = tmp_path / "stamp.json"
    stamp_path.write_text(
        json.dumps(
            {
                "id": "s",
                "width": 3,
                "height": 3,
                "tiles": [],
                "entities": [{"prefab_id": "slime_blob", "x": 1, "y": 1, "id_suffix": "e1"}],
            }
        ),
        encoding="utf-8",
    )

    rc = mesh_cli.main(
        ["scene", "stamp-report", str(scene_path), "--stamp", str(stamp_path), "--x", "10", "--y", "20", "--id-prefix", "demo"]
    )
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["entity_changes"] == [
        {
            "action": "add",
            "id": "scene_demo_e1_10_20_0_0",
            "prefab_id": "slime_blob",
            "x": 184.0,
            "y": 344.0,
        }
    ]

    # Now pre-create the entity with same id/prefab but wrong position => update
    scene_path.write_text(
        json.dumps(
            {
                "tilemap": {"width": 10, "height": 10, "tilewidth": 16, "tileheight": 16, "tile_layers": [{"id": "Ground", "z": -100, "tiles": [0] * 100}]},
                "entities": [{"id": "scene_demo_e1_10_20_0_0", "prefab_id": "slime_blob", "x": 0.0, "y": 0.0}],
            }
        ),
        encoding="utf-8",
    )
    rc2 = mesh_cli.main(
        ["scene", "stamp-report", str(scene_path), "--stamp", str(stamp_path), "--x", "10", "--y", "20", "--id-prefix", "demo"]
    )
    payload2 = json.loads(capsys.readouterr().out)
    assert rc2 == 0
    assert payload2["entity_changes"] == [
        {
            "action": "update",
            "id": "scene_demo_e1_10_20_0_0",
            "prefab_id": "slime_blob",
            "x": 184.0,
            "y": 344.0,
        }
    ]

