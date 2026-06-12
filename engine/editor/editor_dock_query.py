from __future__ import annotations

from typing import Any, cast

from engine.editor.editor_dock_model import DockStateSnapshot
from engine.editor.editor_shell_layout import DOCK_WIDTH

DEFAULT_DOCK_WIDTH = int(DOCK_WIDTH)


def get_dock_snapshot(controller: Any) -> DockStateSnapshot | None:
    dock = getattr(controller, "dock", None)
    if dock is None:
        return None
    getter = getattr(dock, "get_snapshot", None)
    if callable(getter):
        return cast(DockStateSnapshot, getter())
    return None


def get_raw_dock_widths(controller: Any) -> tuple[int, int]:
    """Return raw dock widths from the dock controller if available."""
    dock = getattr(controller, "dock", None)
    if dock is not None:
        get_left = getattr(dock, "get_left_width", None)
        get_right = getattr(dock, "get_right_width", None)
        if callable(get_left) and callable(get_right):
            return (int(get_left()), int(get_right()))
    return (DEFAULT_DOCK_WIDTH, DEFAULT_DOCK_WIDTH)


def get_effective_dock_widths(controller: Any, window_w: int) -> tuple[int, int]:
    """Return effective dock widths (collapsed/maximized aware) if possible."""
    dock = getattr(controller, "dock", None)
    if dock is not None:
        getter = getattr(dock, "get_effective_dock_widths", None)
        if callable(getter):
            result = getter(int(window_w))
            if isinstance(result, tuple) and len(result) == 2:
                return (int(result[0]), int(result[1]))
    getter = getattr(controller, "get_effective_dock_widths", None)
    if callable(getter):
        result = getter(int(window_w))
        if isinstance(result, tuple) and len(result) == 2:
            return (int(result[0]), int(result[1]))
    return get_raw_dock_widths(controller)


def get_dock_collapsed(controller: Any) -> tuple[bool, bool]:
    dock = getattr(controller, "dock", None)
    if dock is not None:
        get_left = getattr(dock, "get_left_collapsed", None)
        get_right = getattr(dock, "get_right_collapsed", None)
        if callable(get_left) and callable(get_right):
            return (bool(get_left()), bool(get_right()))
    return (False, False)


def get_viewport_maximized(controller: Any) -> bool:
    dock = getattr(controller, "dock", None)
    if dock is not None:
        getter = getattr(dock, "get_viewport_maximized", None)
        if callable(getter):
            return bool(getter())
    return False


def get_dock_drag_active(controller: Any) -> str | None:
    dock = getattr(controller, "dock", None)
    if dock is not None:
        getter = getattr(dock, "get_drag_active", None)
        if callable(getter):
            value = getter()
            return value if isinstance(value, str) else None
    return None
