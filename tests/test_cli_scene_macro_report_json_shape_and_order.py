import json
from pathlib import Path

import mesh_cli


def test_cli_scene_macro_report_json_shape_and_order(tmp_path: Path, capsys) -> None:
    scene_path = tmp_path / "scene.json"
    scene_path.write_text(
        json.dumps(
            {
                "tilemap": {
                    "width": 4,
                    "height": 4,
                    "tilewidth": 16,
                    "tileheight": 16,
                    "tile_layers": [{"id": "Ground", "z": -100, "tiles": [0] * 16}],
                },
                "entities": [{"id": "player", "prefab_id": "player", "tags": ["player"], "x": 100.0, "y": 200.0}],
            }
        ),
        encoding="utf-8",
    )

    macro_path = tmp_path / "macro.json"
    macro_path.write_text(
        json.dumps(
            {
                "id": "m",
                "type": "macro",
                "macro_id": "macro.door_transition",
                "defaults": {"anchor": "player", "target_scene": "scenes/x.json", "spawn_id": "entry"},
            }
        ),
        encoding="utf-8",
    )

    rc = mesh_cli.main(["scene", "macro-report", str(scene_path), "--macro", str(macro_path), "--format", "json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["ok"] is True
    assert isinstance(payload["entity_changes"], list)
    assert isinstance(payload["config_changes"], list)

    entity_ids = [row.get("id") for row in payload["entity_changes"]]
    assert entity_ids == sorted(entity_ids)

    cfg_keys = [(row.get("id"), row.get("behaviour"), row.get("field")) for row in payload["config_changes"]]
    assert cfg_keys == sorted(cfg_keys)

