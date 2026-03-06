from __future__ import annotations

import types

import pytest

from engine import optional_arcade
from engine.input import InputManager
from engine.ui import SettingsOverlay

pytestmark = [pytest.mark.fast]


class _Audio:
    def __init__(self) -> None:
        self.master_volume = 1.0
        self.sfx_volume = 1.0
        self.music_volume = 1.0

    def set_master_volume(self, volume: float) -> None:
        self.master_volume = float(volume)

    def set_sfx_volume(self, volume: float) -> None:
        self.sfx_volume = float(volume)

    def set_music_volume(self, volume: float) -> None:
        self.music_volume = float(volume)


def test_settings_overlay_sfx_slider_drag_updates_config_field() -> None:
    manager = InputManager()
    manager.bind("move_up", optional_arcade.arcade.key.W)

    window = types.SimpleNamespace()
    window.width = 800
    window.height = 600
    window.paused = False
    window.audio = _Audio()
    window.engine_config = types.SimpleNamespace(input_bindings={})
    window.input_controller = types.SimpleNamespace(manager=manager)

    overlay = SettingsOverlay(window)  # type: ignore[arg-type]
    overlay.open()
    overlay.settings.music_volume = 0.42
    bounds = overlay._layout_sfx_slider()

    press_x = bounds.left + (bounds.width * 0.2)
    press_y = bounds.center_y
    assert overlay.on_mouse_press(press_x, press_y, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True
    assert overlay.settings.sfx_volume == pytest.approx(0.2, abs=0.02)
    assert window.audio.sfx_volume == pytest.approx(overlay.settings.sfx_volume, abs=1e-9)

    drag_x = bounds.left + (bounds.width * 0.9)
    assert overlay.on_mouse_drag(drag_x, press_y, 0.0, 0.0, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True
    assert overlay.settings.sfx_volume == pytest.approx(0.9, abs=0.02)
    assert window.audio.sfx_volume == pytest.approx(overlay.settings.sfx_volume, abs=1e-9)
    assert overlay.settings.music_volume == pytest.approx(0.42, abs=1e-9)

    assert overlay.on_mouse_release(drag_x, press_y, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True


def test_settings_overlay_master_slider_drag_updates_config_field() -> None:
    manager = InputManager()
    manager.bind("move_up", optional_arcade.arcade.key.W)

    window = types.SimpleNamespace()
    window.width = 800
    window.height = 600
    window.paused = False
    window.audio = _Audio()
    window.engine_config = types.SimpleNamespace(input_bindings={}, master_volume=0.5)
    window.input_controller = types.SimpleNamespace(manager=manager)

    overlay = SettingsOverlay(window)  # type: ignore[arg-type]
    overlay.open()
    bounds = overlay._layout_master_slider()

    press_x = bounds.left + (bounds.width * 0.3)
    press_y = bounds.center_y
    assert overlay.on_mouse_press(press_x, press_y, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True
    assert window.engine_config.master_volume == pytest.approx(0.3, abs=0.02)
    assert window.audio.master_volume == pytest.approx(0.3, abs=0.02)

    drag_x = bounds.left + (bounds.width * 0.85)
    assert overlay.on_mouse_drag(drag_x, press_y, 0.0, 0.0, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True
    assert window.engine_config.master_volume == pytest.approx(0.85, abs=0.02)
    assert window.audio.master_volume == pytest.approx(0.85, abs=0.02)

    assert overlay.on_mouse_release(drag_x, press_y, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True


def test_settings_overlay_music_slider_drag_updates_config_field() -> None:
    manager = InputManager()
    manager.bind("move_up", optional_arcade.arcade.key.W)

    window = types.SimpleNamespace()
    window.width = 800
    window.height = 600
    window.paused = False
    window.audio = _Audio()
    window.engine_config = types.SimpleNamespace(input_bindings={})
    window.input_controller = types.SimpleNamespace(manager=manager)

    overlay = SettingsOverlay(window)  # type: ignore[arg-type]
    overlay.open()
    overlay.settings.sfx_volume = 0.33
    bounds = overlay._layout_music_slider()

    press_x = bounds.left + (bounds.width * 0.25)
    press_y = bounds.center_y
    assert overlay.on_mouse_press(press_x, press_y, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True
    assert overlay.settings.music_volume == pytest.approx(0.25, abs=0.02)
    assert window.audio.music_volume == pytest.approx(0.25, abs=0.02)

    drag_x = bounds.left + (bounds.width * 0.75)
    assert overlay.on_mouse_drag(drag_x, press_y, 0.0, 0.0, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True
    assert overlay.settings.music_volume == pytest.approx(0.75, abs=0.02)
    assert window.audio.music_volume == pytest.approx(0.75, abs=0.02)
    assert overlay.settings.sfx_volume == pytest.approx(0.33, abs=1e-9)

    assert overlay.on_mouse_release(drag_x, press_y, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True


def test_settings_overlay_rumble_slider_drag_updates_config_field() -> None:
    manager = InputManager()
    manager.bind("move_up", optional_arcade.arcade.key.W)

    window = types.SimpleNamespace()
    window.width = 800
    window.height = 600
    window.paused = False
    window.audio = _Audio()
    window.engine_config = types.SimpleNamespace(
        input_bindings={},
        input={"rumble_enabled": True, "rumble_strength": 0.25},
    )
    window.input_controller = types.SimpleNamespace(manager=manager)

    overlay = SettingsOverlay(window)  # type: ignore[arg-type]
    overlay.open()
    bounds = overlay._layout_rumble_slider()

    press_x = bounds.left + (bounds.width * 0.1)
    press_y = bounds.center_y
    assert overlay.on_mouse_press(press_x, press_y, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True
    assert window.engine_config.input["rumble_strength"] == pytest.approx(0.1, abs=0.02)
    assert manager.get_rumble_strength() == pytest.approx(0.1, abs=0.02)

    drag_x = bounds.left + (bounds.width * 0.8)
    assert overlay.on_mouse_drag(drag_x, press_y, 0.0, 0.0, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True
    assert window.engine_config.input["rumble_strength"] == pytest.approx(0.8, abs=0.02)
    assert manager.get_rumble_strength() == pytest.approx(0.8, abs=0.02)

    assert overlay.on_mouse_release(drag_x, press_y, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True


def test_settings_overlay_rumble_toggle_click_updates_config_and_live_apply() -> None:
    manager = InputManager()
    manager.bind("move_up", optional_arcade.arcade.key.W)

    window = types.SimpleNamespace()
    window.width = 800
    window.height = 600
    window.paused = False
    window.audio = _Audio()
    window.engine_config = types.SimpleNamespace(
        input_bindings={},
        input={"rumble_enabled": False, "rumble_strength": 0.3},
    )
    window.input_controller = types.SimpleNamespace(manager=manager)

    overlay = SettingsOverlay(window)  # type: ignore[arg-type]
    overlay.open()
    bounds = overlay._layout_rumble_toggle()

    click_x = bounds.left + 10.0
    click_y = bounds.center_y
    assert overlay.on_mouse_press(click_x, click_y, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True
    assert window.engine_config.input["rumble_enabled"] is True
    assert manager.is_rumble_enabled() is True
    assert manager.get_rumble_strength() == pytest.approx(0.3, abs=1e-9)

    assert overlay.on_mouse_press(click_x, click_y, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True
    assert window.engine_config.input["rumble_enabled"] is False
    assert manager.is_rumble_enabled() is False
