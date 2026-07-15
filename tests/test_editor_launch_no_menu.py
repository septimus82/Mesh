from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from engine.config import EngineConfig
from engine.game import GameWindow
from engine.game_launch import launch_editor
from engine.paths import reset_path_caches
from engine.ui_overlays.main_menu_overlay import MainMenuOverlay


class _DummyWindow:
    def __init__(self, *args, **kwargs) -> None:
        self.width = int(args[0]) if args else int(kwargs.get("width", 800))
        self.height = int(args[1]) if len(args) > 1 else int(kwargs.get("height", 600))
        self._ctx = MagicMock()


@pytest.fixture
def headless_game_window(monkeypatch: pytest.MonkeyPatch):
    import engine.game
    import engine.optional_arcade as optional_arcade
    from engine import arcade_fallback

    original_bases = engine.game.GameWindow.__bases__
    engine.game.GameWindow.__bases__ = (_DummyWindow,)
    monkeypatch.setattr(optional_arcade, "arcade", arcade_fallback)
    try:
        with patch("engine.camera_controller.ArcadeCamera"):
            yield
    finally:
        engine.game.GameWindow.__bases__ = original_bases


def _write_project(root: Path, *, start_scene: str = "scenes/cellar.json", main_menu_scene: str | None = None) -> None:
    (root / "scenes").mkdir(parents=True, exist_ok=True)
    (root / "scenes" / "cellar.json").write_text(json.dumps({"entities": []}), encoding="utf-8")
    (root / "scenes" / "door_field.json").write_text(json.dumps({"entities": []}), encoding="utf-8")
    payload: dict[str, object] = {
        "width": 640,
        "height": 360,
        "title": "Launch Test",
        "start_scene": start_scene,
        "main_menu_scene": main_menu_scene,
        "world_file": None,
    }
    (root / "config.json").write_text(json.dumps(payload), encoding="utf-8")


def test_editor_launch_constructs_no_main_menu_overlay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    headless_game_window,
) -> None:
    _write_project(tmp_path, main_menu_scene="scenes/main_menu.json")
    reset_path_caches()
    loaded: list[str] = []
    windows: list[GameWindow] = []

    def _fake_run(self: GameWindow) -> None:
        windows.append(self)

    def _fake_load_scene(self: GameWindow, scene_path: str):
        loaded.append(scene_path)
        self.scene_controller.current_scene_path = scene_path
        return {}

    with (
        patch("engine.game_launch.GameWindow.run", _fake_run),
        patch("engine.game_launch.GameWindow.load_scene", _fake_load_scene),
    ):
        assert launch_editor(project_root=tmp_path, open_tile_paint=False) == 0

    assert loaded == ["scenes/cellar.json"]
    assert len(windows) == 1
    window = windows[0]
    assert window.main_menu_overlay is None
    assert not any(isinstance(element, MainMenuOverlay) for element in window.ui_controller.ui_elements)
    assert window.editor_controller.active is True


def test_editor_scene_override_sticks_after_enter_dispatch(
    tmp_path: Path,
    headless_game_window,
) -> None:
    _write_project(tmp_path)
    scene_path = "scenes/door_field.json"
    windows: list[GameWindow] = []

    def _fake_run(self: GameWindow) -> None:
        windows.append(self)

    def _fake_load_scene(self: GameWindow, scene: str):
        self.scene_controller.current_scene_path = scene
        return {}

    with (
        patch("engine.game_launch.GameWindow.run", _fake_run),
        patch("engine.game_launch.GameWindow.load_scene", _fake_load_scene),
    ):
        assert launch_editor(project_root=tmp_path, scene_path=scene_path, open_tile_paint=False) == 0

    window = windows[0]
    from engine import arcade_fallback

    for _ in range(5):
        window.on_key_press(arcade_fallback.key.ENTER, 0)
        window.on_text("\n")
        window.on_update(1 / 60)

    assert window.scene_controller.current_scene_path == scene_path
    assert window.main_menu_overlay is None


def test_play_window_still_constructs_menu_and_enter_reaches_it(headless_game_window) -> None:
    cfg = EngineConfig(width=640, height=360, start_scene="scenes/game.json", world_file=None)
    window = GameWindow(cfg.width, cfg.height, cfg.title, config=cfg)
    menu = window.main_menu_overlay
    assert isinstance(menu, MainMenuOverlay)

    menu.visible = True
    menu.state = "main"
    menu._selection_index = 0
    window.game_state_controller = SimpleNamespace(replace_state=lambda _state: None)
    window.request_scene_change = MagicMock()

    from engine import arcade_fallback

    window.on_key_press(arcade_fallback.key.ENTER, 0)

    window.request_scene_change.assert_called_once_with("scenes/game.json")
