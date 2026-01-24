import json
from pathlib import Path

import mesh_cli


def test_cli_scene_macro_apply_prefab_mismatch_errors(tmp_path: Path, capsys) -> None:
    scene_path = tmp_path / "scene.json"
    created_id = "scene_macro_transition_x_100_200_0_0"
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
                "entities": [
                    {"id": "player", "prefab_id": "player", "tags": ["player"], "x": 100.0, "y": 200.0},
                    {"id": created_id, "prefab_id": "crate", "x": 100.0, "y": 200.0},
                ],
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

    before = scene_path.read_text(encoding="utf-8")
    rc = mesh_cli.main(["scene", "macro-apply", str(scene_path), "--macro", str(macro_path)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "prefab_mismatch" in out
    assert scene_path.read_text(encoding="utf-8") == before

