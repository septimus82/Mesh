import json
from pathlib import Path

import mesh_cli


def test_cli_scene_stamp_report_prefab_mismatch_errors(tmp_path: Path, capsys):
    scene_path = tmp_path / "scene.json"
    scene_path.write_text(
        json.dumps(
            {
                "tilemap": {"width": 10, "height": 10, "tilewidth": 16, "tileheight": 16, "tile_layers": [{"id": "Ground", "z": -100, "tiles": [0] * 100}]},
                "entities": [{"id": "scene_demo_e1_10_20_0_0", "prefab_id": "crate", "x": 0.0, "y": 0.0}],
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
    assert rc == 1
    assert "prefab_mismatch" in out
    assert "scene_demo_e1_10_20_0_0" in out

