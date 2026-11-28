"""Studio's play bar (Stop, Flags, Menu) doesn't cover the game's HP bar or objective (#769).

At 800x600 a play-test's bar, centred at the top, ran over the HP bar at the top left (wider still with the AI
permissions' buttons) and over the objective at the top right. The HUD now asks Studio where the bar is
(``Studio.play_bar_rect``, laid out as arcade.gui lays it out to draw it) and starts what's under it just below it.
At 1280x720 with the usual bar nothing collides, and nothing moves.

A real Mesh Studio in a real hidden window, play-testing; the rectangles are the ones the draw itself recorded.
Silent. GL-gated: MESH_GL_SMOKE=1.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from engine import optional_arcade
from tests._game_window_live import dispose_game_window
from tests.test_hud_objective_and_layout_real_window import START, _apart, _project

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1" or not optional_arcade.has_arcade(),
                       reason="real-GPU render test is opt-in (set MESH_GL_SMOKE=1 with a display/GL context)"),
    pytest.mark.filterwarnings("ignore:draw_text is an extremely slow function"),
    pytest.mark.filterwarnings("ignore:UIInputText is now a UIStyledWidget:DeprecationWarning"),
]


@pytest.mark.parametrize(("size", "ai_buttons"), [((800, 600), False), ((800, 600), True), ((1280, 720), False),
                                                  ((1280, 720), True)])
def test_the_play_bar_keeps_clear_of_the_hp_bar_and_objective(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                              size: tuple[int, int], ai_buttons: bool) -> None:
    from engine.config import load_config
    from engine.game import GameWindow
    from engine.repo_root import clear_launched_project_root
    from engine.studio import open_studio

    root = _project(tmp_path / "game")
    monkeypatch.chdir(root)
    monkeypatch.setenv("MESH_SAVE_DIR", str(tmp_path / "saves"))
    monkeypatch.setenv("MESH_RUNTIME_SETTINGS_PATH", str(tmp_path / "user_settings.json"))
    monkeypatch.setenv("MESH_STUDIO_NO_AI_BRIDGE", "1")
    config = load_config(str(root / "config.json"))
    config.tour_completed = True
    window = GameWindow(width=size[0], height=size[1], title=config.title, vsync=False, config=config)
    window._allow_dispatch_event = True  # (pyglet queues a hidden window's events outside its own loop otherwise)
    studio = None
    try:
        window.audio.set_muted(True)
        window.load_scene(START)
        world = json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"]
        studio = open_studio(window, root, world, START)
        assert studio is not None
        studio.ai.playtest_control = studio.ai.gameplay_control = ai_buttons  # (two more buttons on the bar)
        studio.play()
        assert window.quest_manager.start_quest("oil") is True
        for _ in range(3):
            window.dispatch_event("on_update", 1 / 60)
            window.dispatch_event("on_draw")
        bar = studio.play_bar_rect()
        drawn = window.player_hud.drawn
        assert bar is not None and {"hp", "objective"} <= set(drawn), drawn
        for kind in ("hp", "objective"):
            rect = drawn[kind][1:]
            assert _apart(rect, bar), f"the play bar {bar} covers the {kind} {rect} at {size}"
        if size == (1280, 720) and not ai_buttons:  # (nothing in the way: everything where it always was)
            assert drawn["hp"][4] == 720 - 28 and drawn["objective"][4] == 720 - 20, drawn
        studio.stop()
        window.dispatch_event("on_draw")
        assert studio.play_bar_rect() is None
    finally:
        if studio is not None:
            studio.release_project()
        dispose_game_window(window)
        clear_launched_project_root()
