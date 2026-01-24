import json
from pathlib import Path

import mesh_cli


def test_cli_scene_macro_report_includes_entity_and_config_changes_sorted(tmp_path: Path, capsys) -> None:
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

    assert payload["scene_path"] == str(scene_path).replace("\\", "/")
    assert payload["macro_path"] == str(macro_path).replace("\\", "/")
    assert payload["create_ids"] == sorted(payload["create_ids"])
    assert payload["update_ids"] == sorted(payload["update_ids"])
    assert payload["entity_changes"] and payload["config_changes"]

    entity_changes = payload["entity_changes"]
    assert [row["id"] for row in entity_changes] == sorted(row["id"] for row in entity_changes)
    row = entity_changes[0]
    assert set(row.keys()) == {
        "id",
        "action",
        "prefab_id",
        "name",
        "tags",
        "require_flags",
        "forbid_flags",
        "x",
        "y",
        "behaviours_added",
        "behaviours_removed",
    }
    assert row["action"] == "add"
    assert row["prefab_id"] == "SceneTransition"
    assert row["behaviours_added"] == ["SceneTransition"]
    assert row["behaviours_removed"] == []

    config_changes = payload["config_changes"]
    cfg_keys = [(row["id"], row["behaviour"], row["field"]) for row in config_changes]
    assert cfg_keys == sorted(cfg_keys)
    assert {row["field"] for row in config_changes if row["behaviour"] == "SceneTransition"} == {
        "spawn_id",
        "spawn_point",
        "target_scene",
    }
