from __future__ import annotations

from dataclasses import dataclass, field

import arcade

from engine.game_runtime import input_dispatch, tick


@dataclass
class _StubUIController:
    consume: bool = False
    events: list[str] = field(default_factory=list)

    def on_key_press(self, _key: int, _modifiers: int) -> bool:
        self.events.append("ui")
        return self.consume

    def update(self, _dt: float) -> None:
        self.events.append("ui_update")


@dataclass
class _StubInputController:
    events: list[str] = field(default_factory=list)

    def on_key_press(self, _key: int, _modifiers: int) -> bool:
        self.events.append("input_key")
        return False

    def update(self, _dt: float) -> None:
        self.events.append("input_update")

    def on_key_release(self, _key: int, _modifiers: int) -> bool:
        self.events.append("input_key_release")
        return False

    def on_mouse_motion(self, *_a) -> None:
        self.events.append("mouse_motion")

    def on_mouse_drag(self, *_a) -> None:
        self.events.append("mouse_drag")

    def on_mouse_release(self, *_a) -> None:
        self.events.append("mouse_release")

    def on_mouse_press(self, *_a) -> None:
        self.events.append("mouse_press")

    def on_text(self, *_a) -> None:
        self.events.append("text")


@dataclass
class _StubPauseMenu:
    events: list[str] = field(default_factory=list)
    visible: bool = False

    def toggle(self) -> None:
        self.events.append("pause_toggle")


@dataclass
class _StubEngineConfig:
    debug_mode: bool = False


@dataclass
class _StubWindow:
    ui_controller: _StubUIController
    input_controller: _StubInputController
    pause_menu: _StubPauseMenu
    engine_config: _StubEngineConfig = field(default_factory=_StubEngineConfig)
    paused: bool = False
    game_over: bool = False
    console_messages: list[str] = field(default_factory=list)

    def console_log(self, message: str) -> None:
        self.console_messages.append(message)

    @property
    def input(self):
        raise AssertionError("input should not be accessed in this regression test")


def test_modal_ui_consumes_escape_before_pause_toggle() -> None:
    ui = _StubUIController(consume=True)
    inp = _StubInputController()
    pause_menu = _StubPauseMenu()
    window = _StubWindow(ui_controller=ui, input_controller=inp, pause_menu=pause_menu)

    input_dispatch.on_key_press(window, arcade.key.ESCAPE, 0)

    assert window.paused is False
    assert pause_menu.events == []
    assert inp.events == []
    assert ui.events == ["ui"]


def test_escape_toggles_pause_when_unconsumed_and_preserves_order() -> None:
    events: list[str] = []
    ui = _StubUIController(consume=False, events=events)
    inp = _StubInputController(events=events)
    pause_menu = _StubPauseMenu(events=events)
    window = _StubWindow(ui_controller=ui, input_controller=inp, pause_menu=pause_menu)

    input_dispatch.on_key_press(window, arcade.key.ESCAPE, 0)

    assert events == ["ui", "input_key", "pause_toggle"]
    assert window.paused is True
    assert window.pause_menu.visible is True
    assert window.console_messages == ["Game Paused"]


def test_tick_updates_input_before_early_paused_return() -> None:
    events: list[str] = []
    ui = _StubUIController(consume=False, events=events)
    inp = _StubInputController(events=events)
    pause_menu = _StubPauseMenu()
    window = _StubWindow(ui_controller=ui, input_controller=inp, pause_menu=pause_menu)
    window.paused = True

    tick.on_update(window, 0.016)

    assert events == ["input_update", "ui_update"]

