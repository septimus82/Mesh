from __future__ import annotations

from typing import TYPE_CHECKING, Any

from engine.logging_tools import get_logger
from engine.paths import is_path_under_content_roots, resolve_path
from engine.scene_transition_policy_model import (
    SceneTransitionRequest,
    decide_scene_transition,
)

if TYPE_CHECKING:
    from engine.game import GameWindow


logger = get_logger(__name__)


def resolve_game_start_scene(
    *,
    engine_config: Any,
    world_controller: Any | None,
) -> str | None:
    """Resolve the playable start scene for the active project.

  Prefer the loaded project world's start scene when it points at an existing
  file under the project's content roots. Otherwise fall back to
  ``engine_config.start_scene`` so engine/default worlds cannot leak in.
    """
    cfg_scene = str(getattr(engine_config, "start_scene", "") or "").strip() or None
    if world_controller is None:
        return cfg_scene

    getter = getattr(world_controller, "get_start_scene_key", None)
    start_key = getter() if callable(getter) else None
    if not start_key:
        return cfg_scene

    path_getter = getattr(world_controller, "get_scene_path", None)
    if not callable(path_getter):
        return cfg_scene

    try:
        world_scene = str(path_getter(start_key) or "").strip() or None
    except Exception:
        return cfg_scene

    if not world_scene:
        return cfg_scene

    resolved = resolve_path(world_scene)
    if not resolved.exists() or not is_path_under_content_roots(resolved):
        return cfg_scene

    return world_scene


def load_scene(window: "GameWindow", scene_path: str) -> dict[str, Any]:
    """Load entities from a JSON scene file and build sprites for them."""
    return window.scene_controller.load_scene(scene_path)


def request_scene_reload(window: "GameWindow", *, clear_assets: bool = False) -> None:
    """Request that the currently loaded scene reload on the next frame."""
    window.scene_controller.request_scene_reload(clear_assets)


def request_reload_current_scene(window: "GameWindow", *, clear_assets: bool = False) -> None:
    """Request that the currently loaded scene reload on the next frame."""
    window.request_scene_reload(clear_assets=clear_assets)


def request_scene_change(window: "GameWindow", scene_path: str) -> None:
    """Request that a different scene load on the next frame."""
    controller = window.scene_controller
    editor = getattr(window, "editor_controller", None)
    is_editor = bool(editor is not None and getattr(editor, "active", False))
    has_unsaved = False
    if is_editor and editor is not None:
        dirty_state = getattr(editor, "dirty_state", None)
        has_unsaved = bool(getattr(dirty_state, "is_dirty", False))
    req = SceneTransitionRequest(
        from_scene_path=getattr(controller, "current_scene_path", None),
        to_scene_path=str(scene_path),
        reason="Switch Scene",
        is_editor=is_editor,
        has_unsaved_changes=has_unsaved,
    )
    decision = decide_scene_transition(req)
    if decision.allowed:
        controller.request_scene_change(scene_path)
        return
    if decision.requires_confirm and editor is not None:
        blocker = getattr(editor, "confirm_unsaved_changes", None)
        if callable(blocker):
            blocked = blocker("Switch Scene", lambda: controller.request_scene_change(scene_path))
            if isinstance(blocked, bool) and blocked:
                return
    controller.request_scene_change(scene_path)


def queue_scene_change(window: "GameWindow", scene_path: str, *, spawn_id: str | None = None) -> None:
    """Request that the game switches to another scene at the end of the frame."""
    controller = window.scene_controller
    editor = getattr(window, "editor_controller", None)
    is_editor = bool(editor is not None and getattr(editor, "active", False))
    has_unsaved = False
    if is_editor and editor is not None:
        dirty_state = getattr(editor, "dirty_state", None)
        has_unsaved = bool(getattr(dirty_state, "is_dirty", False))
    req = SceneTransitionRequest(
        from_scene_path=getattr(controller, "current_scene_path", None),
        to_scene_path=str(scene_path),
        reason="Switch Scene",
        is_editor=is_editor,
        has_unsaved_changes=has_unsaved,
    )
    decision = decide_scene_transition(req)
    if decision.allowed:
        controller.queue_scene_change(scene_path, spawn_id=spawn_id)
        return
    if decision.requires_confirm and editor is not None:
        blocker = getattr(editor, "confirm_unsaved_changes", None)
        if callable(blocker):
            blocked = blocker(
                "Switch Scene",
                lambda: controller.queue_scene_change(scene_path, spawn_id=spawn_id),
            )
            if isinstance(blocked, bool) and blocked:
                return
    controller.queue_scene_change(scene_path, spawn_id=spawn_id)


def reload_scene(window: "GameWindow", new_path: str | None = None) -> bool:
    """Hot reload the current (or provided) scene immediately."""
    window.particle_manager.clear()
    return window.scene_controller.reload_scene(new_path)


def reload_current_scene(window: "GameWindow") -> None:
    """Debug: Reload the current scene from disk."""
    logger.info("[Mesh][Debug] Reloading current scene...")
    reload_scene(window)


def warp_to_scene(window: "GameWindow", scene_path: str) -> None:
    """Debug: Warp to a specific scene."""
    logger.info("[Mesh][Debug] Warping to %s...", scene_path)
    request_scene_change(window, scene_path)
