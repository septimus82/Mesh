from __future__ import annotations

import types

import engine.optional_arcade as optional_arcade

from engine.game_runtime import input_dispatch


def test_console_processes_enter_even_when_ui_consumes_keys(monkeypatch) -> None:
    calls: list[str] = []

    class _UI:
        def on_key_press(self, _key: int, _mod: int) -> bool:
            calls.append("ui")
            return True

    class _Console:
        active = True

        def process_key(self, key: int, _mod: int) -> bool:
            if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
                calls.append("console")
                return True
            return False

    window = types.SimpleNamespace(ui_controller=_UI(), console_controller=_Console())
    input_dispatch.on_key_press(window, optional_arcade.arcade.key.RETURN, 0)
    assert calls == ["console"]

