import json
from pathlib import Path

from engine.ai_ops import AIOps


def test_add_entity_from_prefab(tmp_path: Path):
    scene = {
        "layers": [{"name": "background"}, {"name": "entities"}],
        "entities": [],
    }
    scene_path = tmp_path / "scene.json"
    scene_path.write_text(json.dumps(scene), encoding="utf-8")

    prefab_payload = [
        {
            "display_name": "Crate",
            "entity": {"name": "Crate", "sprite": "assets/placeholder.png", "layer": "entities"},
        }
    ]
    prefab_path = tmp_path / "prefabs.json"
    prefab_path.write_text(json.dumps(prefab_payload), encoding="utf-8")

    ops = AIOps(tmp_path)
    result = ops.add_entity_from_prefab(str(scene_path), "Crate", 10, 20, prefab_path=str(prefab_path))
    assert result.ok

    updated = json.loads(scene_path.read_text(encoding="utf-8"))
    assert len(updated["entities"]) == 1
    entity = updated["entities"][0]
    assert entity["x"] == 10.0 and entity["y"] == 20.0
    assert entity["name"].startswith("Crate")


def test_paint_tiles(tmp_path: Path):
    map_json = {"width": 2, "height": 2}
    map_path = tmp_path / "map.json"
    map_path.write_text(json.dumps(map_json), encoding="utf-8")

    scene = {
        "tilemap": {"path": str(map_path)},
        "entities": [],
    }
    scene_path = tmp_path / "scene.json"
    scene_path.write_text(json.dumps(scene), encoding="utf-8")

    ops = AIOps(tmp_path)
    result = ops.paint_tiles(str(scene_path), [{"layer": "ground", "col": 1, "row": 0, "gid": 5}])
    assert result.ok

    updated = json.loads(scene_path.read_text(encoding="utf-8"))
    layers = updated["tilemap"]["overrides"]["layers"]
    data = layers["ground"]
    assert data[1] == 5


def test_apply_job(tmp_path: Path):
    scene = {"entities": []}
    scene_path = tmp_path / "scene.json"
    scene_path.write_text(json.dumps(scene), encoding="utf-8")

    job = {
        "operations": [
            {"type": "set_behaviour_params", "scene_path": str(scene_path), "entity_id": "Missing", "behaviour_name": "Foo", "params": {}},
            {"type": "run_validation", "scene_path": str(scene_path)},
        ]
    }
    ops = AIOps(tmp_path)
    result = ops.apply_job(job)
    assert result["ok"] is False
    assert len(result["results"]) == 2
