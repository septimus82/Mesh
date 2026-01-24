from __future__ import annotations

from types import SimpleNamespace

import pytest

import engine.optional_arcade as optional_arcade
from engine.input import InputManager
from engine.ui_overlays.menus import PauseMenu


class _StubAudio:
    def __init__(self) -> None:
        self.music_calls: list[float] = []
        self.sfx_calls: list[float] = []

    def set_music_volume(self, volume: float) -> None:
        self.music_calls.append(float(volume))

    def set_sfx_volume(self, volume: float) -> None:
        self.sfx_calls.append(float(volume))

    def play_sound(self, _path: str) -> None:
        return


class _StubSaveManager:
    def list_saves(self) -> list[str]:
        return []

    def save_game(self, _slot: str) -> bool:
        return True

    def load_game(self, _slot: str) -> bool:
        return True


def _make_window():
    cfg = SimpleNamespace(
        music_volume=0.5,
        sfx_volume=0.5,
        fog_enabled=False,
        soft_shadows_enabled=False,
    )
    audio = _StubAudio()
    window = SimpleNamespace(
        width=800,
        height=600,
        audio=audio,
        engine_config=cfg,
        paused=True,
        save_manager=_StubSaveManager(),
    )
    return window, audio, cfg


@pytest.mark.fast
def test_pause_menu_settings_volume_clamps_and_applies(monkeypatch) -> None:
    from engine import arcade_fallback as arcade_stub

    monkeypatch.setattr(optional_arcade, "arcade", arcade_stub)

    window, audio, cfg = _make_window()
    menu = PauseMenu(window)  # type: ignore[arg-type]
    menu.visible = True
    menu.state = "settings"
    menu._settings_index = 0

    menu.on_key_press(optional_arcade.arcade.key.RIGHT, 0)
    assert window.runtime_settings.music_volume > 0.5
    assert audio.music_calls
    assert cfg.music_volume == pytest.approx(window.runtime_settings.music_volume)

    window.runtime_settings.music_volume = 0.02
    menu.on_key_press(optional_arcade.arcade.key.LEFT, optional_arcade.arcade.key.MOD_SHIFT)
    assert window.runtime_settings.music_volume == 0.0


@pytest.mark.fast
def test_pause_menu_settings_toggles_fog_and_shadows(monkeypatch) -> None:
    from engine import arcade_fallback as arcade_stub

    monkeypatch.setattr(optional_arcade, "arcade", arcade_stub)

    window, _audio, cfg = _make_window()
    menu = PauseMenu(window)  # type: ignore[arg-type]
    menu.visible = True
    menu.state = "settings"

    menu._settings_index = 2
    menu.on_key_press(optional_arcade.arcade.key.ENTER, 0)
    assert window.runtime_settings.fog_enabled is True
    assert cfg.fog_enabled is True

    menu._settings_index = 3
    menu.on_key_press(optional_arcade.arcade.key.ENTER, 0)
    assert window.runtime_settings.soft_shadows_enabled is True
    assert cfg.soft_shadows_enabled is True


@pytest.mark.fast
def test_pause_menu_settings_gamepad_navigation(monkeypatch) -> None:
    from engine import arcade_fallback as arcade_stub

    monkeypatch.setattr(optional_arcade, "arcade", arcade_stub)

    window, _audio, _cfg = _make_window()
    manager = InputManager()
    window.input = manager

    menu = PauseMenu(window)  # type: ignore[arg-type]
    menu.visible = True
    menu.state = "settings"
    menu._settings_index = 0

    manager.set_gamepad_state(
        actions_down={"move_down"},
        axis_values={("move_left", "move_right"): 0.0, ("move_down", "move_up"): 0.0},
        supported_actions={"move_down", "move_up", "move_left", "move_right"},
        source_active=True,
    )
    manager.update(0.016)
    menu.update(0.016)
    assert menu._settings_index == 1
