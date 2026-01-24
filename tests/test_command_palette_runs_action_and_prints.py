from __future__ import annotations

import engine.optional_arcade as optional_arcade


def test_command_palette_runs_action_and_prints(capsys, monkeypatch) -> None:
    from engine.input_runtime import capture as input_capture
    from engine.palette_mode import get_state

    palette = get_state()
    original_enabled = bool(palette.enabled)
    palette.enabled = False
    try:
        called: list[str] = []

        def _action(_w, _arg):
            called.append("ran")

        from engine.command_palette import CommandSpec

        monkeypatch.setattr(
            "engine.command_palette.build_default_commands",
            lambda _w: [
                CommandSpec(
                    id="x",
                    title="Do Thing",
                    section="Test",
                    keywords=("thing",),
                    is_enabled=lambda _w2: (True, ""),
                    prompt=None,
                    action=_action,
                    hotkey_hint="X",
                ),
            ],
        )

        class _Window:
            show_debug = True
            command_palette_enabled = True
            command_palette_query = "do"
            command_palette_index = 0
            command_palette_prompt_active = False
            ui_controller = type("U", (), {"on_key_press": lambda *_a: False, "input_blocked": False})()
            console_controller = type("C", (), {"active": False, "toggle": lambda *_a: None})()
            editor_controller = type("E", (), {"active": False})()

        window = _Window()

        class _Mgr:
            def press(self, *_a):  # pragma: no cover
                raise AssertionError("should not dispatch gameplay input")

        controller = type("Ctl", (), {"window": window, "manager": _Mgr(), "_keys": set()})()

        assert input_capture.handle_key_press(controller, optional_arcade.arcade.key.ENTER, 0) is True
        out = capsys.readouterr().out.strip()
        assert out == "PALETTE_RUN ok id=x title=Do Thing"
        assert called == ["ran"]
        assert window.command_palette_enabled is False
    finally:
        palette.enabled = original_enabled

