from __future__ import annotations

import types

import arcade

from engine.input import InputManager
from engine.ui import SettingsOverlay
from tests._typing import as_any


class _Audio:
    def __init__(self) -> None:
        self.sfx_volume = 1.0
        self.music_volume = 1.0

    def set_sfx_volume(self, volume: float) -> None:
        self.sfx_volume = float(volume)

    def set_music_volume(self, volume: float) -> None:
        self.music_volume = float(volume)


def test_settings_overlay_remaps_key_and_persists(monkeypatch, tmp_path) -> None:  # noqa: ANN001
    settings_path = tmp_path / "settings.json"
    monkeypatch.setenv("MESH_SETTINGS_PATH", str(settings_path))

    manager = InputManager()
    manager.bind("move_up", arcade.key.W)
    manager.bind("interact", arcade.key.E)

    window = types.SimpleNamespace()
    window.width = 800
    window.height = 600
    window.paused = False
    window.audio = _Audio()
    window.engine_config = types.SimpleNamespace(input_bindings={})
    window.input_controller = types.SimpleNamespace(manager=manager)

    overlay = SettingsOverlay(as_any(window))
    overlay.apply()

    overlay.open()
    assert overlay.visible is True

    # Select "move_up" row (index 0), enter capture mode, then bind K.
    overlay.on_key_press(arcade.key.ENTER, 0)
    overlay.on_key_press(arcade.key.K, 0)
    assert manager.get_bindings()["move_up"] == [arcade.key.K]

    # Adjust SFX volume down once (move to row and press LEFT).
    overlay.on_key_press(arcade.key.DOWN, 0)
    overlay.on_key_press(arcade.key.DOWN, 0)
    overlay.on_key_press(arcade.key.DOWN, 0)
    overlay.on_key_press(arcade.key.DOWN, 0)
    overlay.on_key_press(arcade.key.DOWN, 0)
    overlay.on_key_press(arcade.key.DOWN, 0)  # now on SFX row
    overlay.on_key_press(arcade.key.LEFT, 0)
    assert 0.0 <= window.audio.sfx_volume <= 1.0

    overlay.close()
    assert overlay.visible is False

    from engine.settings import load_settings

    saved = load_settings(settings_path)
    assert saved.keybinds["move_up"] == arcade.key.K
