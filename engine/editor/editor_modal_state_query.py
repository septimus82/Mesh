from __future__ import annotations

from typing import Any


def get_active_menu_id(controller: Any) -> str | None:
    return getattr(controller, "_menu_active", None)


def is_scene_browser_active(controller: Any) -> bool:
    return bool(getattr(controller, "scene_browser_active", False))


def is_unsaved_changes_pending(controller: Any) -> bool:
    return bool(getattr(controller, "_unsaved_changes_pending", False))


def is_dock_shell_active(window: Any) -> bool:
    controller = getattr(window, "editor_controller", None)
    if controller is None or not getattr(controller, "active", False):
        return False
    return getattr(window, "editor_shell_overlay", None) is not None
