from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from tests._typing import as_any


class EditorWindowStub:
    def __init__(
        self,
        *,
        scene_controller: object,
        width: int = 800,
        height: int = 600,
        paused: bool = False,
        strict_mode: bool = False,
        zoom: float = 1.0,
        mouse_x: float = 0.0,
        mouse_y: float = 0.0,
        **extra_attrs: Any,
    ) -> None:
        self.strict_mode = bool(strict_mode)
        self.paused = bool(paused)
        self.width = int(width)
        self.height = int(height)
        self._mouse_x = float(mouse_x)
        self._mouse_y = float(mouse_y)
        self.scene_controller = scene_controller
        self.camera_controller = SimpleNamespace(zoom=float(zoom))
        self.screen_to_world = lambda x, y: (float(x), float(y))
        for key, value in extra_attrs.items():
            setattr(self, key, value)


def as_game_window(window: EditorWindowStub) -> Any:
    return as_any(window)
