from __future__ import annotations

import json
from contextlib import ExitStack
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from engine.config import EngineConfig, load_config
from engine.game import GameWindow

pytestmark = pytest.mark.fast


def _noop(*_: Any, **__: Any) -> None:
    return None


def _build_window(
    *,
    config: EngineConfig | None = None,
    resizable: bool | None = None,
    minimum_size: Any = _noop,
    day_night_calls: list[dict[str, Any]] | None = None,
) -> tuple[GameWindow, dict[str, Any], list[tuple[int, int]]]:
    init_kwargs: dict[str, Any] = {}
    min_calls: list[tuple[int, int]] = []

    def mock_window_init(self: Any, *args: Any, **kwargs: Any) -> None:
        init_kwargs.update(kwargs)
        self._width = int(kwargs.get("width", args[0] if args else 800))
        self._height = int(kwargs.get("height", args[1] if len(args) > 1 else 600))

    def mock_set_minimum_size(self: Any, width: int, height: int) -> None:
        min_calls.append((width, height))

    audio = SimpleNamespace(set_master_volume=_noop, set_sfx_volume=_noop, set_music_volume=_noop)
    light = SimpleNamespace(set_ambient_tint=_noop, set_ambient_darkness_alpha=_noop, resize=_noop)
    watcher = SimpleNamespace(configure_polling=_noop)
    simple_classes = (
        "SceneLoader",
        "AssetManager",
        "AnimationFactory",
        "TilemapManager",
        "ConsoleController",
        "CameraController",
        "SceneController",
        "InputController",
        "UIController",
        "GameStateController",
        "SaveManager",
        "QuestManager",
        "ParticleManager",
        "EditorModeController",
        "AIDebugOverlay",
        "ArcadeSpriteBatcher",
        "SpriteRenderQueue",
    )

    def build_day_night(*_: Any, **kwargs: Any) -> SimpleNamespace:
        if day_night_calls is not None:
            day_night_calls.append(dict(kwargs))
        return SimpleNamespace()

    with ExitStack() as stack:
        stack.enter_context(patch("arcade.Window.__init__", side_effect=mock_window_init, autospec=True))
        stack.enter_context(patch("arcade.Window.get_size", lambda self: (self._width, self._height)))
        if minimum_size is None:
            stack.enter_context(patch.object(GameWindow, "set_minimum_size", None))
        else:
            stack.enter_context(
                patch.object(GameWindow, "set_minimum_size", mock_set_minimum_size, create=True)
            )
        stack.enter_context(patch("arcade.set_background_color"))
        stack.enter_context(patch("arcade.Text", return_value=SimpleNamespace(y=0)))
        stack.enter_context(patch("engine.game.load_builtin_behaviours"))
        stack.enter_context(patch("engine.game._init_audio_coordinator", lambda window, audio_manager_cls: None))
        stack.enter_context(patch("engine.game._init_ui_dispatcher", _noop))
        stack.enter_context(patch("engine.game.AudioManager", return_value=audio))
        stack.enter_context(patch("engine.game.LightManager", return_value=light))
        stack.enter_context(patch("engine.game.CutsceneController", return_value=SimpleNamespace(load_from_file=_noop)))
        stack.enter_context(patch("engine.game.build_fx_preset_registry", return_value={}))
        stack.enter_context(patch("engine.game.build_input_service", return_value=SimpleNamespace()))
        stack.enter_context(patch("engine.game.build_persistence_service", return_value=SimpleNamespace()))
        stack.enter_context(patch("engine.game.build_replay_service", return_value=SimpleNamespace()))
        stack.enter_context(patch("engine.asset_hot_reload_watcher.maybe_start_hot_reload_watcher", return_value=watcher))
        stack.enter_context(patch("engine.post_processing.PostProcessPipeline", return_value=SimpleNamespace()))
        stack.enter_context(patch("engine.plugin_system.PluginManager", return_value=SimpleNamespace(load_all=_noop, enable_all=_noop)))
        stack.enter_context(patch("engine.game.DayNightCycle", side_effect=build_day_night))
        for class_name in simple_classes:
            stack.enter_context(patch(f"engine.game.{class_name}", return_value=SimpleNamespace()))

        kwargs: dict[str, Any] = {"config": config}
        if resizable is not None:
            kwargs["resizable"] = resizable
        window = GameWindow(800, 600, "Resize Contract", **kwargs)

    return window, init_kwargs, min_calls


def test_engine_config_resizable_defaults_true() -> None:
    assert EngineConfig().resizable is True


def test_existing_config_without_resizable_loads_default_true(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"width": 800, "height": 600, "title": "Existing", "start_scene": "scenes/cellar.json"}),
        encoding="utf-8",
    )

    config = load_config(str(path))

    assert config.resizable is True


def test_game_window_forwards_resizable_true_by_default() -> None:
    window, init_kwargs, _ = _build_window()

    assert init_kwargs["resizable"] is True
    assert window.engine_config.resizable is True


def test_game_window_forwards_config_resizable_false() -> None:
    config = EngineConfig(resizable=False)
    window, init_kwargs, _ = _build_window(config=config)

    assert init_kwargs["resizable"] is False
    assert window.engine_config.resizable is False


def test_game_window_explicit_resizable_false_beats_config_true() -> None:
    config = EngineConfig(resizable=True)
    window, init_kwargs, _ = _build_window(config=config, resizable=False)

    assert init_kwargs["resizable"] is False
    assert window.engine_config.resizable is False


def test_game_window_passes_canonical_day_night_config_to_cycle() -> None:
    day_night_calls: list[dict[str, Any]] = []
    config = EngineConfig(
        day_night_enabled=True,
        day_night_start_hour=7.5,
        day_night_cycle_length_seconds=1200.0,
    )

    _build_window(config=config, day_night_calls=day_night_calls)

    assert day_night_calls == [{
        "enabled": True,
        "start_hour": 7.5,
        "cycle_length_seconds": 1200.0,
    }]


def test_game_window_sets_guarded_minimum_size_and_tolerates_missing_method() -> None:
    _, _, min_calls = _build_window()
    _build_window(minimum_size=None)

    assert min_calls == [(480, 270)]


def test_game_window_on_resize_updates_config_and_forwards_hooks() -> None:
    calls: list[tuple[str, int, int]] = []

    class _Hook:
        def __init__(self, name: str) -> None:
            self.name = name

        def on_resize(self, width: int, height: int) -> None:
            calls.append((self.name, width, height))

        def resize(self, width: int, height: int) -> None:
            calls.append((self.name, width, height))

    window = GameWindow.__new__(GameWindow)
    window.engine_config = EngineConfig(width=800, height=600)
    window.console_visible_line_count = 0
    window.camera_controller = _Hook("camera")
    window.ui_controller = _Hook("ui")
    window.editor_controller = _Hook("editor")
    window.lighting = _Hook("lighting")
    window._debug_text = SimpleNamespace(y=0)
    window._height = 900
    window._width = 1600

    with patch("arcade.Window.on_resize", lambda self, width, height: None):
        window.on_resize(1600, 900)

    assert window.engine_config.width == 1600
    assert window.engine_config.height == 900
    assert calls == [
        ("camera", 1600, 900),
        ("ui", 1600, 900),
        ("editor", 1600, 900),
        ("lighting", 1600, 900),
    ]
