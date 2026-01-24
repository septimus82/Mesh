"""Mesh Engine package.

Keep this module import-side-effect-free.

Many tools and CLI commands import lightweight helpers from `engine.*` modules.
Importing those should not implicitly pull in the full game/editor stack.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

__all__ = ["GameWindow", "SceneLoader"]
__version__ = "0.1.0"

if TYPE_CHECKING:
    from .game import GameWindow as GameWindow
    from .scene_loader import SceneLoader as SceneLoader


def __getattr__(name: str):
    if name == "GameWindow":
        return import_module(".game", __name__).GameWindow
    if name == "SceneLoader":
        return import_module(".scene_loader", __name__).SceneLoader
    raise AttributeError(name)


def __dir__() -> list[str]:
    return sorted(set(globals().keys()) | set(__all__))
