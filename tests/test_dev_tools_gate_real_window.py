"""#664: a game launch has no developer tools, through the real keys of a real (hidden) GameWindow.

In an exported game the console's ``dumpstate <path>`` overwrote any file the player could write, and F3 debug mode
(then Ctrl+Shift+S, Ctrl+S, or tile/entity paint, or the Ctrl+F1 palette) saved the room over the shipped one so the
game no longer started. The console and debug mode now open only where ``dev_tools_allowed``: ``mesh play`` (launch
mode "play"), ``mesh edit`` (launch mode "editor"), MESH_LEGACY_EDITOR=1. A game as players run it has neither.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import engine.optional_arcade as optional_arcade
from tests.test_legacy_editor_gate_real_window import _close, _window

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]

CONFIG = b'{"title": "the shipped game"}\n'


def _launch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str | None, *, env: bool = False,
            **config: Any) -> Any:
    if env:
        monkeypatch.setenv("MESH_LEGACY_EDITOR", "1")
    else:
        monkeypatch.delenv("MESH_LEGACY_EDITOR", raising=False)
    window = _window(tmp_path, monkeypatch, mode, **config)
    (tmp_path / "config.json").write_bytes(CONFIG)
    return window


def _press(window: Any, symbol: int, mods: int = 0) -> None:
    window.dispatch_event("on_key_press", symbol, mods)
    window.dispatch_event("on_key_release", symbol, mods)
    window.on_update(1 / 60)


def _type(window: Any, text: str) -> None:
    for ch in text:
        window.dispatch_event("on_text", ch)


def _console(window: Any, command: str) -> None:
    key = optional_arcade.arcade.key
    _press(window, key.GRAVE)
    _type(window, command)
    _press(window, key.ENTER)


def _persist(window: Any) -> None:
    key = optional_arcade.arcade.key
    _press(window, key.S, key.MOD_CTRL | key.MOD_SHIFT)  # arm
    _press(window, key.S, key.MOD_CTRL)  # save


def _paint_then_persist(window: Any, toggle: int) -> None:
    key = optional_arcade.arcade.key
    _press(window, key.F3)
    _press(window, toggle)
    for x, y in ((160, 100), (100, 80), (220, 120)):
        window.dispatch_event("on_mouse_press", x, y, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0)
        window.dispatch_event("on_mouse_release", x, y, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0)
    _press(window, toggle)
    _persist(window)


# --------------------------------------------------------------------- a game launch: nothing opens, nothing written

def test_the_console_never_opens_in_a_game_launch_so_dumpstate_writes_nothing(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    window = _launch(tmp_path, monkeypatch, None)
    outside = tmp_path / "elsewhere" / "victim.json"  # (an absolute path: any file the player can write)
    try:
        key = optional_arcade.arcade.key
        for symbol in (key.GRAVE, key.INSERT, key.F1):
            _press(window, symbol)
            assert window.console_controller.active is False
        _console(window, "dumpstate config.json")
        _console(window, f"dumpstate {outside}")
        _console(window, "dump_scene config.json")
        assert window.console_controller.active is False
        assert (tmp_path / "config.json").read_bytes() == CONFIG
        assert not outside.parent.exists()
    finally:
        _close(window)


@pytest.mark.parametrize("route", ["persist", "tile_paint", "entity_paint", "palette"])
def test_f3_debug_never_turns_on_in_a_game_launch_so_the_room_is_never_saved(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, route: str) -> None:
    window = _launch(tmp_path, monkeypatch, None)
    room = tmp_path / "room.json"
    shipped = room.read_bytes()
    key = optional_arcade.arcade.key
    try:
        if route == "persist":
            _press(window, key.F3)
            _persist(window)
        elif route == "tile_paint":
            _paint_then_persist(window, key.F11)
        elif route == "entity_paint":
            _paint_then_persist(window, key.HOME)
        else:  # Ctrl+F1 command palette: arm, then save
            _press(window, key.F3)
            for query in ("scene.persist_arm", "scene.persist"):
                _press(window, key.F1, key.MOD_CTRL)
                _type(window, query)
                _press(window, key.ENTER)
            assert window.command_palette_enabled is False
        assert window.show_debug is False
        assert not getattr(window, "scene_persist_armed", False)
        assert room.read_bytes() == shipped
        assert {p.name for p in tmp_path.iterdir()} <= {"assets", "config.json", "room.json", "saves"}  # (no save-as)
    finally:
        _close(window)


def test_a_projects_debug_on_start_never_ships_debug_mode_to_its_players(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    window = _launch(tmp_path, monkeypatch, None, debug_on_start=True)
    try:
        assert window.show_debug is False
    finally:
        _close(window)


# --------------------------------------------------------------------- dev launches keep their tools

@pytest.mark.parametrize("mode,env", [("play", False), ("editor", False), (None, True)],
                         ids=["mesh play", "mesh edit", "MESH_LEGACY_EDITOR=1"])
def test_dev_launches_keep_the_console_and_debug_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                      mode: str | None, env: bool) -> None:
    window = _launch(tmp_path, monkeypatch, mode, env=env)
    key = optional_arcade.arcade.key
    try:
        _press(window, key.GRAVE)
        assert window.console_controller.active is True
        _press(window, key.GRAVE)
        _press(window, key.F3)
        assert window.show_debug is True
    finally:
        _close(window)


def test_mesh_play_still_dumps_state_and_saves_the_room(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The same keys reach the writers in a dev launch (so the game-launch tests above test a real refusal)."""
    window = _launch(tmp_path, monkeypatch, "play", debug_on_start=True)
    room = tmp_path / "room.json"
    before = room.read_bytes()
    try:
        assert window.show_debug is True
        _persist(window)
        assert room.read_bytes() != before and json.loads(room.read_text(encoding="utf-8"))["name"] == "Room"
        _console(window, "dumpstate dump.json")
        assert (tmp_path / "dump.json").is_file()
    finally:
        _close(window)


def test_mesh_play_is_a_dev_launch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``mesh play`` (a developer's CLI: exports ship no mesh_cli) launches with mode "play"; main.py sets none."""
    import argparse

    from engine.paths import reset_path_caches
    from mesh_cli import misc

    seen: list[Any] = []

    class _Window:
        def __init__(self, **kwargs: Any) -> None:
            seen.append(kwargs["config"])

        def load_scene(self, _path: str) -> None:
            raise RuntimeError("(stops before the window loop)")

    monkeypatch.setattr("engine.game.GameWindow", _Window)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    reset_path_caches()
    try:
        assert misc._handle_play(argparse.Namespace(scene_path=None)) == 1
    finally:
        reset_path_caches()
    assert getattr(seen[0], "_mesh_launch_mode", None) == "play"
