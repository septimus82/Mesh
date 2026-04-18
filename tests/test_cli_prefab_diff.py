from __future__ import annotations

import json
from pathlib import Path

import mesh_cli

from engine.paths import get_content_roots, set_content_roots


def _write_prefab_scene(tmp_path: Path) -> None:
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


def test_cli_prefab_diff_text(tmp_path: Path, capsys) -> None:
    original_roots = get_content_roots()
    set_content_roots([tmp_path])
    try:
        _write_prefab_scene(tmp_path)
        rc = mesh_cli.main(
            [
                "scene",
                "prefab-diff",
                "--scene",
                "scenes/test_scene.json",
                "--entity",
                "ent1",
            ]
        )
        assert rc == 0
        out = capsys.readouterr().out
        assert "sprite" in out
        assert "tag" in out
    finally:
        set_content_roots(original_roots)


def test_cli_prefab_diff_json(tmp_path: Path, capsys) -> None:
    original_roots = get_content_roots()
    set_content_roots([tmp_path])
    try:
        _write_prefab_scene(tmp_path)
        rc = mesh_cli.main(
            [
                "scene",
                "prefab-diff",
                "--scene",
                "scenes/test_scene.json",
                "--entity",
                "ent1",
                "--format",
                "json",
            ]
        )
        assert rc == 0
        out = capsys.readouterr().out
        payload = json.loads(out)
        field_paths = {item["field_path"] for item in payload["overrides"]}
        assert "sprite" in field_paths
        assert "tag" in field_paths
    finally:
        set_content_roots(original_roots)
