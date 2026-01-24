import json
from pathlib import Path

import mesh_cli


def test_cli_scene_macro_apply_idempotent(tmp_path: Path, capsys) -> None:
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

    before = scene_path.read_text(encoding="utf-8")
    rc1 = mesh_cli.main(["scene", "macro-apply", str(scene_path), "--macro", str(macro_path)])
    out1 = capsys.readouterr().out
    assert rc1 == 0
    assert "OK: macro applied" in out1
    after1 = scene_path.read_text(encoding="utf-8")
    assert after1 != before

    rc2 = mesh_cli.main(["scene", "macro-apply", str(scene_path), "--macro", str(macro_path)])
    capsys.readouterr()
    assert rc2 == 0
    after2 = scene_path.read_text(encoding="utf-8")
    assert after2 == after1

    payload = json.loads(after2)
    created_id = "scene_macro_transition_x_100_200_0_0"
    ent = next(e for e in payload["entities"] if e.get("id") == created_id)
    assert "SceneTransition" in (ent.get("behaviours") or [])
    assert ent["behaviour_config"]["SceneTransition"]["target_scene"] == "scenes/x.json"
    assert ent["behaviour_config"]["SceneTransition"]["spawn_id"] == "entry"

