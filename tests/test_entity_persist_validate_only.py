from __future__ import annotations

import arcade


def test_entity_paint_validate_only_does_not_write(tmp_path, capsys) -> None:
    from engine.entity_paint_mode import EntityPaintState
    from engine.input_runtime import capture as input_capture

    class _Console:
        active = False

    class _UI:
        def on_key_press(self, _key: int, _mod: int) -> bool:
            return False

    class _SceneController:
        def __init__(self, path: str) -> None:
            self.current_scene_path = path

        def get_authored_scene_payload(self):
            return {"entities": []}

    scene_path = tmp_path / "scene.json"
    state = EntityPaintState()
    state.enabled = True
    state.persist_armed = True

    window = type(
        "W",
        (),
        {
            "console_controller": _Console(),
            "ui_controller": _UI(),
            "show_debug": True,
            "entity_paint_state": state,
            "scene_controller": _SceneController(str(scene_path)),
        },
    )()
    controller = type("C", (), {"window": window})()

    assert input_capture.handle_key_press(controller, arcade.key.ENTER, arcade.key.MOD_CTRL) is True
    out = capsys.readouterr().out.strip()
    assert out == "ENTITY_VALIDATE ok errors=0"
    assert scene_path.exists() is False

