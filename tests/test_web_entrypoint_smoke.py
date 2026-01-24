from __future__ import annotations

from dataclasses import dataclass

import pytest

import web_main


@dataclass
class _StubConfig:
    width: int = 640
    height: int = 480
    title: str = "Mesh Web"
    fullscreen: bool = False
    vsync: bool = True
    start_scene: str = "scenes/cellar.json"
    main_menu_scene: str | None = None


class _StubWindow:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


@pytest.mark.fast
def test_web_entrypoint_create_window_is_patchable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(web_main, "_load_game_window", lambda: _StubWindow)
    config = _StubConfig()
    window = web_main.create_window(config=config, config_path="config.json")
    assert isinstance(window, _StubWindow)
    assert window.kwargs["width"] == config.width
    assert window.kwargs["height"] == config.height
    assert window.kwargs["title"] == config.title
    assert window.kwargs["fullscreen"] == config.fullscreen
    assert window.kwargs["vsync"] == config.vsync
