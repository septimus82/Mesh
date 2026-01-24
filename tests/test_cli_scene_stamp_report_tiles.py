import json
from pathlib import Path

import mesh_cli


def test_cli_scene_stamp_report_tiles_sorted_and_exact(tmp_path: Path, capsys):
    scene_path = tmp_path / "scene.json"
    w, h = 6, 4
    tiles = [0] * (w * h)
    tiles[1 + 1 * w] = 2  # (1,1)
    scene_path.write_text(
        json.dumps(
            {
                "tilemap": {
                    "width": w,
                    "height": h,
                    "tilewidth": 16,
                    "tileheight": 16,
                    "tile_layers": [{"id": "Ground", "z": -100, "tiles": tiles}],
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
                "id": "s",
                "width": 2,
                "height": 2,
                "tiles": [{"layer_id": "Ground", "x": 0, "y": 0, "w": 2, "h": 1, "tile": 5}],
                "entities": [],
            }
        ),
        encoding="utf-8",
    )

    rc = mesh_cli.main(
        [
            "scene",
            "stamp-report",
            str(scene_path),
            "--stamp",
            str(stamp_path),
            "--x",
            "1",
            "--y",
            "1",
            "--format",
            "json",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["origin"] == {"x": 1, "y": 1}
    assert payload["tile_changes"] == [
        {"after": 5, "before": 2, "layer_id": "Ground", "x": 1, "y": 1},
        {"after": 5, "before": 0, "layer_id": "Ground", "x": 2, "y": 1},
    ]
    assert payload["entity_changes"] == []
