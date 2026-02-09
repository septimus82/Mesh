from __future__ import annotations

import engine.optional_arcade as optional_arcade


def test_command_palette_go_to_scene_runs_request_change(capsys, monkeypatch) -> None:
    from engine.input_runtime import capture as input_capture
    from engine.palette_mode import get_state

    palette = get_state()
    original_enabled = bool(palette.enabled)
    palette.enabled = False
    try:
        monkeypatch.setattr("engine.scene_index.iter_known_scene_paths", lambda: ["scenes/a.json", "scenes/b.json"])

        requested: list[str] = []

        class _SceneController:
            current_scene_path = "scenes/start.json"

        def _request_scene_change(scene_path: str) -> None:
            requested.append(str(scene_path))

        class _Window:
            show_debug = True
            command_palette_enabled = True
            command_palette_query = "go"
            command_palette_index = 0
            command_palette_prompt_active = False
            scene_controller = _SceneController()
            ui_controller = type("U", (), {"on_key_press": lambda *_a: False, "input_blocked": False})()
            console_controller = type("C", (), {"active": False, "toggle": lambda *_a: None})()
            editor_controller = type("E", (), {"active": False})()
            request_scene_change = staticmethod(_request_scene_change)

        window = _Window()
        controller = type("Ctl", (), {"window": window, "manager": type("M", (), {"press": lambda *_a: None})(), "_keys": set()})()

        # Enter opens pick prompt for Go To Scene.
        assert input_capture.handle_key_press(controller, optional_arcade.arcade.key.ENTER, 0) is True
        assert window.command_palette_prompt_active is True
        assert str(getattr(window, "command_palette_prompt_kind", "")) == "pick"

        # Type a prompt filter to choose scenes/b.json.
        input_capture.handle_text(controller, "b")

        # Confirm selection.
        assert input_capture.handle_key_press(controller, optional_arcade.arcade.key.ENTER, 0) is True
        out = capsys.readouterr().out.strip().splitlines()
        assert out[-1] == "PALETTE_RUN ok id=scene.goto title=Go To Scene"
        assert requested == ["scenes/b.json"]
    finally:
        palette.enabled = original_enabled

