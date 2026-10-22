"""A real EditorController on a headless window, launched the way `mesh edit` does."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from engine.game_launch import launch_editor
from engine.project_scaffold import create_project


class _DummyWindow:
    def __init__(self, *args, **kwargs) -> None:
        self.width = int(args[0]) if args else int(kwargs.get("width", 800))
        self.height = int(args[1]) if len(args) > 1 else int(kwargs.get("height", 600))
        self._ctx = MagicMock()


def _default_camera(*_args, **_kwargs) -> MagicMock:
    # arcade's Camera2D starts centred on the window: world (x, y) == screen (x, y).
    camera = MagicMock()
    camera.position = (640.0, 360.0)
    camera.zoom = 1.0
    return camera


@contextmanager
def headless_editor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, template_id: str = "starter") -> Iterator:
    import engine.game
    import engine.optional_arcade as optional_arcade
    from engine import arcade_fallback

    root = tmp_path / "project"
    create_project(root, "project", template_id=template_id)
    monkeypatch.setattr(optional_arcade, "arcade", arcade_fallback)
    original_bases = engine.game.GameWindow.__bases__
    engine.game.GameWindow.__bases__ = (_DummyWindow,)
    windows: list = []
    try:
        with (
            patch("engine.camera_controller.ArcadeCamera", side_effect=_default_camera),
            patch("engine.game_launch.GameWindow.run", lambda self: windows.append(self)),
        ):
            assert launch_editor(project_root=root, open_tile_paint=False) == 0
        yield windows[0]
    finally:
        engine.game.GameWindow.__bases__ = original_bases
