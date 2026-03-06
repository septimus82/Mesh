"""Scene switching/open-load-reload delegation helpers for SceneController."""
from __future__ import annotations

from typing import Any, Callable


def load_scene(
    controller: Any,
    scene_path: str,
    *,
    load_scene_runtime: Callable[[Any, str], dict[str, Any]],
) -> dict[str, Any]:
    return load_scene_runtime(controller, scene_path)


def request_scene_reload(
    controller: Any,
    *,
    clear_assets: bool = False,
    request_scene_reload_runtime: Callable[..., Any],
) -> None:
    request_scene_reload_runtime(controller, clear_assets=clear_assets)


def request_scene_change(
    controller: Any,
    scene_path: str,
    *,
    request_scene_change_runtime: Callable[[Any, str], None],
) -> None:
    request_scene_change_runtime(controller, scene_path)


def queue_scene_change(
    controller: Any,
    scene_path: str,
    *,
    spawn_id: str | None = None,
    queue_scene_change_runtime: Callable[..., None],
) -> None:
    queue_scene_change_runtime(controller, scene_path, spawn_id=spawn_id)


def perform_scene_change(
    controller: Any,
    scene_path: str,
    *,
    spawn_id: str | None = None,
    perform_scene_change_runtime: Callable[..., None],
) -> None:
    perform_scene_change_runtime(controller, scene_path, spawn_id=spawn_id)


def reload_scene(
    controller: Any,
    *,
    new_path: str | None = None,
    reload_scene_runtime: Callable[..., bool],
) -> bool:
    return bool(reload_scene_runtime(controller, new_path=new_path))


def reload_current_scene(
    controller: Any,
    *,
    reload_scene_runtime: Callable[..., bool],
) -> bool:
    return bool(reload_scene_runtime(controller, new_path=controller.current_scene_path))

