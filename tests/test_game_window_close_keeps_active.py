"""Closing one GameWindow never takes the active window away from another (Milestone 13).

Arcade forgets the active window whenever any window closes, and pyglet closes a window when it is garbage-
collected: a leftover window collected at an unpredictable moment left the window in use without a context
("No window is active"), the intermittent failure of the viewport and editor-launch tests. The windows here are
real but hidden (tests/conftest.py).
"""

from __future__ import annotations

import pytest

import engine.optional_arcade as optional_arcade
from engine.config import EngineConfig
from tests._game_window_live import dispose_game_window

pytestmark = pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")


def _window():
    from engine.game import GameWindow

    cfg = EngineConfig(width=320, height=200, title="close contract", vsync=False, start_scene="", world_file=None,
                       main_menu_scene=None)
    return GameWindow(width=320, height=200, title=cfg.title, vsync=False, config=cfg)


def test_closing_a_window_that_isnt_active_keeps_the_active_one() -> None:
    first = _window()
    second = _window()  # the active window now
    try:
        first.close()
        assert optional_arcade.arcade.get_window() is second
    finally:
        dispose_game_window(second)
