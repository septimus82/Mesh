from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.scene_loader import SceneLoader

pytestmark = pytest.mark.builtin_behaviours

def test_prefab_shape_inheritance(tmp_path: Path, monkeypatch) -> None:
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
                "test",
            ],
            "entity": {
                "sprite": "assets/placeholder.png",
                "collision_poly": [[0, 0], [8, 0], [0, 8]],
                "occluder_poly": [[-4, -4], [4, -4], [4, 4], [-4, 4]],
            },
        }
    ]
    prefabs_path.write_text(json.dumps(prefabs_payload), encoding="utf-8")

    scene_path = scenes_dir / "test_scene.json"
    scene_payload = {
        "name": "TestScene",
        "entities": [
            {"prefab_id": "p_wall", "x": 10.0, "y": 20.0},
            {
                "prefab_id": "p_wall",
                "x": 30.0,
                "y": 40.0,
                "collision_poly": [[1, 1], [2, 1], [1, 2]],
            },
        ],
    }
    scene_path.write_text(json.dumps(scene_payload), encoding="utf-8")

    def fake_resolve_path(path: str) -> Path:
        if path == "assets/prefabs.json":
            return prefabs_path
        if path == "scenes/test_scene.json":
            return scene_path
        return tmp_path / path

    monkeypatch.setattr("engine.scene_loader.resolve_path", fake_resolve_path)
    monkeypatch.setattr("engine.prefabs.resolve_path", fake_resolve_path)
    monkeypatch.setattr("engine.prefabs.get_content_roots", lambda: [tmp_path])

    loader = SceneLoader()
    loaded = loader.load_scene("scenes/test_scene.json")
    entities = loaded.get("entities", [])

    assert entities[0]["collision_poly"] == [[0, 0], [8, 0], [0, 8]]
    assert entities[0]["occluder_poly"] == [[-4, -4], [4, -4], [4, 4], [-4, 4]]

    assert entities[1]["collision_poly"] == [[1, 1], [2, 1], [1, 2]]
    assert entities[1]["occluder_poly"] == [[-4, -4], [4, -4], [4, 4], [-4, 4]]

    prefabs_after = json.loads(prefabs_path.read_text(encoding="utf-8"))
    assert prefabs_after == prefabs_payload
