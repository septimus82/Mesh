# mypy: ignore-errors
from __future__ import annotations

from engine import scene_controller_scene_switch as _scene_switch
from engine.scene_runtime.transitions import perform_scene_change as _perform_scene_change_runtime
from engine.scene_runtime.transitions import queue_scene_change as _queue_scene_change_runtime
from engine.scene_runtime.transitions import reload_scene as _reload_scene_runtime
from engine.scene_runtime.transitions import request_scene_change as _request_scene_change_runtime
from engine.scene_runtime.transitions import request_scene_reload as _request_scene_reload_runtime


def request_scene_reload(self, clear_assets: bool = False) -> None:
    """Request that the currently loaded scene reload on the next frame."""
    _scene_switch.request_scene_reload(self, clear_assets=clear_assets, request_scene_reload_runtime=_request_scene_reload_runtime)


def request_scene_change(self, scene_path: str) -> None:
    """Request that a different scene load on the next frame."""
    _scene_switch.request_scene_change(self, scene_path, request_scene_change_runtime=_request_scene_change_runtime)


def queue_scene_change(self, scene_path: str, spawn_id: str | None = None) -> None:
    """Request that the game switches to another scene at the end of the frame."""
    _scene_switch.queue_scene_change(self, scene_path, spawn_id=spawn_id, queue_scene_change_runtime=_queue_scene_change_runtime)


def _perform_scene_change(self, scene_path: str, spawn_id: str | None = None) -> None:
    """Load a new scene immediately and apply the requested spawn."""
    _scene_switch.perform_scene_change(self, scene_path, spawn_id=spawn_id, perform_scene_change_runtime=_perform_scene_change_runtime)


def reload_scene(self, new_path: str | None = None) -> bool:
    """Hot reload the current (or provided) scene immediately."""
    return _scene_switch.reload_scene(self, new_path=new_path, reload_scene_runtime=_reload_scene_runtime)


def reload_current_scene(self) -> bool:
    """Hot reload the current scene immediately."""
    return _scene_switch.reload_current_scene(self, reload_scene_runtime=_reload_scene_runtime)

def bind_transitions_methods(cls) -> None:
    cls.request_scene_reload = request_scene_reload
    cls.request_scene_change = request_scene_change
    cls.queue_scene_change = queue_scene_change
    cls._perform_scene_change = _perform_scene_change
    cls.reload_scene = reload_scene
    cls.reload_current_scene = reload_current_scene
