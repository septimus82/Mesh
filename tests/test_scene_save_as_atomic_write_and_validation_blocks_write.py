from __future__ import annotations


def test_scene_save_as_atomic_write_and_validation_blocks_write(tmp_path) -> None:
    from engine.game import GameWindow

    class _SceneController:
        current_scene_path = str(tmp_path / "source.json")

        def __init__(self, payload: dict) -> None:
            self._payload = payload

        def get_authored_scene_payload(self) -> dict:
            return self._payload

    # Valid write uses atomic temp + replace (no leftover .tmp).
    valid_window = type(
        "W",
        (),
        {
            "scene_persist_armed": True,
            "scene_controller": _SceneController({"name": "Ok", "entities": []}),
        },
    )()
    out_ok = tmp_path / "out_ok.json"
    result_ok = GameWindow.save_scene_as(valid_window, str(out_ok))
    assert bool(getattr(result_ok, "ok", False)) is True
    assert out_ok.exists()
    assert not (tmp_path / "out_ok.json.tmp").exists()

    # Invalid payload blocks write.
    invalid_window = type(
        "W",
        (),
        {
            "scene_persist_armed": True,
            "scene_controller": _SceneController({"name": "Bad", "entities": "not-a-list"}),
        },
    )()
    out_bad = tmp_path / "out_bad.json"
    result_bad = GameWindow.save_scene_as(invalid_window, str(out_bad))
    assert bool(getattr(result_bad, "ok", False)) is False
    assert not out_bad.exists()

