from __future__ import annotations

import json


def test_scene_save_as_writes_authored_payload_only(tmp_path) -> None:
    from engine.game import GameWindow
    from engine.scene_serializer import compact_scene_payload

    authored = {
        "name": "Authored",
        "entities": [{"id": "a", "prefab_id": "crate", "x": 1.0, "y": 2.0, "layer": "entities"}],
    }
    runtime_baked = {
        **authored,
        "entities": authored["entities"] + [{"id": "runtime_spawn", "prefab_id": "slime_blob", "x": 9.0, "y": 9.0, "layer": "entities"}],
    }

    class _SceneController:
        current_scene_path = str(tmp_path / "source_scene.json")

        def __init__(self) -> None:
            self._loaded_scene_data = runtime_baked

        def get_authored_scene_payload(self) -> dict:
            return authored

    window = type("W", (), {"scene_persist_armed": True, "scene_controller": _SceneController()})()
    out_path = tmp_path / "copy_scene.json"

    result = GameWindow.save_scene_as(window, str(out_path))
    assert bool(getattr(result, "ok", False)) is True

    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written == compact_scene_payload(authored)
    assert "runtime_spawn" not in json.dumps(written)

