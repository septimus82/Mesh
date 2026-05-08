from __future__ import annotations

from contextlib import ExitStack
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from engine.config import EngineConfig
from engine.game import GameWindow


pytestmark = pytest.mark.fast


SCENE_FACING_ATTRS = (
    "event_bus", "_mesh_event_queue", "_scene_event_unsubscribes", "game_state_controller",
    "save_manager", "quest_manager", "particle_manager",
)


class _FakeSceneController:
    def __init__(self, window: Any) -> None:
        self.window = window
        self.loaded_paths: list[str] = []

    def load_scene(self, scene_path: str) -> dict[str, Any]:
        if not hasattr(self.window, "game_state_controller"):
            raise AttributeError("'GameWindow' object has no attribute 'game_state_controller'")
        self.loaded_paths.append(scene_path)
        return {"path": scene_path}


def _noop(*_: Any) -> None: pass


def _build_window_with_editor_restore(editor_cls: type) -> GameWindow:
    def mock_window_init(self: Any, width: int, height: int, *args: Any, **kwargs: Any) -> None:
        self._width, self._height = width, height

    audio = SimpleNamespace(set_master_volume=_noop, set_sfx_volume=_noop, set_music_volume=_noop)
    light = SimpleNamespace(set_ambient_tint=_noop, set_ambient_darkness_alpha=_noop)
    simple_classes = (
        "SceneLoader", "AssetManager", "AnimationFactory", "TilemapManager", "ConsoleController",
        "CameraController", "InputController", "GameStateController", "SaveManager", "QuestManager",
        "ParticleManager", "DayNightCycle",
    )
    patches = [
        patch("arcade.Window.__init__", side_effect=mock_window_init, autospec=True),
        patch("arcade.Window.get_size", lambda self: (self._width, self._height)),
        patch("arcade.set_background_color"),
        patch("arcade.Text"),
        patch("engine.game.AudioManager", return_value=audio),
        patch("engine.game.SceneController", _FakeSceneController),
        patch("engine.game.UIController", return_value=MagicMock()),
        patch("engine.game.LightManager", return_value=light),
        patch("engine.game.CutsceneController", return_value=SimpleNamespace(load_from_file=_noop)),
        patch("engine.game.EditorModeController", editor_cls),
        patch("engine.asset_hot_reload_watcher.maybe_start_hot_reload_watcher", return_value=None),
    ]
    with ExitStack() as stack:
        for class_name in simple_classes:
            stack.enter_context(patch(f"engine.game.{class_name}", return_value=SimpleNamespace()))
        for item in patches:
            stack.enter_context(item)
        return GameWindow(800, 600, "Init Order", config=EngineConfig())


def test_editor_startup_restore_can_load_scene_mid_game_window_init(caplog) -> None:
    calls: list[str] = []
    observed: dict[str, bool] = {}

    class RestoringEditor:
        def __init__(self, window: GameWindow) -> None:
            observed.update({name: getattr(window, name, None) is not None for name in SCENE_FACING_ATTRS})
            calls.append(window.load_scene("scenes/test_scene.json")["path"])

    _build_window_with_editor_restore(RestoringEditor)

    assert calls == ["scenes/test_scene.json"]
    assert observed == {name: True for name in SCENE_FACING_ATTRS}
    assert "no attribute 'game_state_controller'" not in caplog.text


def test_scene_facing_runtime_attrs_exist_after_game_window_init() -> None:
    class PassiveEditor:
        def __init__(self, window: GameWindow) -> None: self.window = window
    window = _build_window_with_editor_restore(PassiveEditor)
    assert all(getattr(window, name, None) is not None for name in SCENE_FACING_ATTRS)


def test_mid_init_scene_load_uses_initialized_scene_state() -> None:
    class LoadingEditor:
        def __init__(self, window: GameWindow) -> None:
            window.load_scene("scenes/test_scene.json")
    window = _build_window_with_editor_restore(LoadingEditor)
    assert window.scene_controller.loaded_paths == ["scenes/test_scene.json"]
