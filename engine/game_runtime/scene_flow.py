from __future__ import annotations

from typing import TYPE_CHECKING, Any

from engine.logging_tools import get_logger


if TYPE_CHECKING:
    from engine.game import GameWindow


logger = get_logger(__name__)


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
    window.scene_controller.request_scene_change(scene_path)


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
