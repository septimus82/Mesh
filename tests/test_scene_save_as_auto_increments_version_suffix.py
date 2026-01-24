from __future__ import annotations

import json


def test_scene_save_as_auto_increments_version_suffix(tmp_path) -> None:
    from engine.game import GameWindow

    authored = {"name": "Authored", "entities": []}

    class _SceneController:
        current_scene_path = str(tmp_path / "foo.json")

        def get_authored_scene_payload(self) -> dict:
            return authored

    window = type("W", (), {"scene_persist_armed": True, "scene_controller": _SceneController()})()

    # Pre-create v001 with different contents so auto-name moves to v002.
    (tmp_path / "foo__v001.json").write_text(json.dumps({"name": "Different", "entities": []}), encoding="utf-8")

    result = GameWindow.save_scene_as(window, "")
    assert bool(getattr(result, "ok", False)) is True
    assert str(getattr(result, "path", "")).endswith("foo__v002.json")
    assert (tmp_path / "foo__v002.json").exists()

