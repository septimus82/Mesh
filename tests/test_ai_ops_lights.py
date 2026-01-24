import json
from pathlib import Path

from engine.ai_ops import AIOps


def test_add_light_creates_array(tmp_path: Path):
    scene_path = tmp_path / "scene.json"
    scene_path.write_text(json.dumps({"entities": []}), encoding="utf-8")
    ops = AIOps(tmp_path)
    res = ops.add_light(str(scene_path), {"x": 10, "y": 20})
    assert res.ok
    scene = json.loads(scene_path.read_text(encoding="utf-8"))
    lights = scene.get("lights")
    assert isinstance(lights, list)
    assert len(lights) == 1
    light = lights[0]
    assert light["x"] == 10.0 and light["y"] == 20.0
    assert light["radius"] == 160.0
    assert light["mode"] == "soft"


def test_update_light(tmp_path: Path):
    scene_path = tmp_path / "scene.json"
    scene = {"lights": [{"x": 0, "y": 0, "radius": 100, "color": "#fff", "mode": "soft"}]}
    scene_path.write_text(json.dumps(scene), encoding="utf-8")
    ops = AIOps(tmp_path)
    res = ops.update_light(str(scene_path), 0, {"radius": 300})
    assert res.ok
    updated = json.loads(scene_path.read_text(encoding="utf-8"))
    assert updated["lights"][0]["radius"] == 300.0
    assert updated["lights"][0]["mode"] == "soft"


def test_delete_light(tmp_path: Path):
    scene_path = tmp_path / "scene.json"
    scene = {"lights": [{"x": 0, "y": 0, "radius": 100, "color": "#fff", "mode": "soft"}]}
    scene_path.write_text(json.dumps(scene), encoding="utf-8")
    ops = AIOps(tmp_path)
    res = ops.delete_light(str(scene_path), 0)
    assert res.ok
    updated = json.loads(scene_path.read_text(encoding="utf-8"))
    assert updated["lights"] == []
