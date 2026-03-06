# mypy: ignore-errors
from __future__ import annotations

from typing import Any, Dict

from engine import scene_controller_scene_switch as _scene_switch
from engine.pathfinding import NavGrid
from engine.scene_lifecycle_controller import load_scene as _load_scene_runtime


def load_scene(self, scene_path: str) -> Dict[str, Any]:
    """Load entities from a JSON scene file and build sprites for them."""
    return _scene_switch.load_scene(self, scene_path, load_scene_runtime=_load_scene_runtime)


def get_nav_grid(self) -> NavGrid | None:
    scene_path = self.current_scene_path
    revision = int(getattr(self.window, "scene_dirty_counter", 0) or 0)
    return self.navigation.get_nav_grid(scene_path=scene_path, revision=revision, tilemap_instance=self.tilemap_instance)


@property
def current_scene_data(self) -> Dict[str, Any] | None:
    """
    Best-effort access to the current authored scene payload for authoring tools.

    Prefers the pre-runtime copy so persisting does not bake runtime-only mutations
    (e.g. themed placeholder resolution).
    """
    if isinstance(getattr(self, "_loaded_scene_source_data", None), dict):
        return self._loaded_scene_source_data
    if isinstance(getattr(self, "_loaded_scene_data", None), dict):
        return self._loaded_scene_data
    return None

def bind_loading_methods(cls) -> None:
    cls.load_scene = load_scene
    cls.get_nav_grid = get_nav_grid
    cls.current_scene_data = current_scene_data
