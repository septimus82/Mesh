from __future__ import annotations

import json
from pathlib import Path

import mesh_cli
from engine.paths import get_content_roots, set_content_roots


def _write_prefab_scene(tmp_path: Path) -> Path:
    assets_dir = tmp_path / "assets"
    scenes_dir = tmp_path / "scenes"
    assets_dir.mkdir()
    scenes_dir.mkdir()

    prefabs_path = assets_dir / "prefabs.json"
    prefabs_payload = [
        {
            "display_name": "Wall",
            "id": "p_wall",
            "tags": [
                "wall",
            ],
            "entity": {
                "sprite": "base.png",
                "tag": "wall",
            },
        }
    ]
    prefabs_path.write_text(json.dumps(prefabs_payload), encoding="utf-8")

    scene_path = scenes_dir / "test_scene.json"
    scene_payload = {
        "name": "TestScene",
        "entities": [
            {
                "id": "ent1",
                "prefab_id": "p_wall",
                "x": 1.0,
                "y": 2.0,
                "sprite": "override.png",
                "tag": "crate",
            }
        ],
    }
    scene_path.write_text(json.dumps(scene_payload), encoding="utf-8")
    return scene_path


def test_cli_prefab_reset_field_and_all(tmp_path: Path, capsys) -> None:
    original_roots = get_content_roots()
    set_content_roots([tmp_path])
    try:
        scene_path = _write_prefab_scene(tmp_path)

        rc = mesh_cli.main(
            [
                "scene",
                "prefab-reset",
                "--scene",
                "scenes/test_scene.json",
                "--entity",
                "ent1",
                "--field",
                "sprite",
            ]
        )
        assert rc == 0
        capsys.readouterr()
        payload = json.loads(scene_path.read_text(encoding="utf-8"))
        ent = payload["entities"][0]
        assert ent["sprite"] == "base.png"
        assert ent["tag"] == "crate"

        rc2 = mesh_cli.main(
            [
                "scene",
                "prefab-reset",
                "--scene",
                "scenes/test_scene.json",
                "--entity",
                "ent1",
                "--all",
            ]
        )
        assert rc2 == 0
        capsys.readouterr()
        payload2 = json.loads(scene_path.read_text(encoding="utf-8"))
        ent2 = payload2["entities"][0]
        assert ent2["sprite"] == "base.png"
        assert ent2["tag"] == "wall"

        rc3 = mesh_cli.main(
            [
                "scene",
                "prefab-diff",
                "--scene",
                "scenes/test_scene.json",
                "--entity",
                "ent1",
            ]
        )
        assert rc3 == 0
        out = capsys.readouterr().out
        assert "no overrides" in out
    finally:
        set_content_roots(original_roots)
