from __future__ import annotations

from typing import Any


def get_active_menu_id(controller: Any) -> str | None:
    return getattr(controller, "_menu_active", None)


def is_scene_browser_active(controller: Any) -> bool:
    return bool(getattr(controller, "scene_browser_active", False))


def is_unsaved_changes_pending(controller: Any) -> bool:
    return bool(getattr(controller, "_unsaved_changes_pending", False))
