"""Cursor application helper for editor affordance.

This module provides a small, headless-safe helper that maps cursor kinds
to arcade system cursors and applies them with caching.
"""

from __future__ import annotations

from typing import Any

import engine.optional_arcade as optional_arcade


_SWALLOW_ONCE_TAGS: set[str] = set()

def _log_swallow(tag: str, context: str, *, once: bool = True) -> None:
    if once and tag in _SWALLOW_ONCE_TAGS:
        return
    if once:
        _SWALLOW_ONCE_TAGS.add(tag)
    from engine.logging_tools import get_logger

    get_logger(__name__).debug("SWALLOW[%s] %s", tag, context, exc_info=True)


def apply_editor_cursor(window: Any, cursor_kind: str | None) -> None:
    """Apply cursor kind to the window (best-effort).

    Args:
        window: Game window or stub with cursor API.
        cursor_kind: Cursor kind string ("default", "pointer", "move",
            "resize_h", "resize_v", "crosshair").
    """
    arcade = optional_arcade.arcade
    if arcade is None or window is None:
        return

    kind = cursor_kind or "default"
    last_kind = getattr(window, "_last_cursor_kind", None)
    if last_kind == kind:
        return

    cursor = _resolve_system_cursor(arcade, kind)
    if cursor is None:
        return

    setter = getattr(window, "set_mouse_cursor", None)
    if callable(setter):
        try:
            setter(cursor)
            setattr(window, "_last_cursor_kind", kind)
            return
        except Exception:  # noqa: BLE001  # REASON: window cursor setter failures should not break editor input handling
            _log_swallow("EDIT-001", "engine/editor/editor_cursor_apply.py pass-only blanket swallow")
            pass

    setter = getattr(arcade, "set_mouse_cursor", None)
    if callable(setter):
        try:
            setter(cursor)
            setattr(window, "_last_cursor_kind", kind)
        except Exception:  # noqa: BLE001  # REASON: arcade cursor fallback failures should not break editor input handling
            _log_swallow("EDIT-002", "engine/editor/editor_cursor_apply.py pass-only blanket swallow")
            pass


def _resolve_system_cursor(arcade: Any, cursor_kind: str) -> Any:
    """Resolve arcade SystemMouseCursor from a cursor kind string."""
    system_cursors = getattr(arcade, "SystemMouseCursor", None)
    if system_cursors is None:
        return None

    mapping = {
        "default": "DEFAULT",
        "pointer": "HAND",
        "move": "MOVE",
        "resize_h": "SIZE_WE",
        "resize_v": "SIZE_NS",
        "crosshair": "CROSSHAIR",
    }
    cursor_name = mapping.get(cursor_kind, "DEFAULT")
    cursor = getattr(system_cursors, cursor_name, None)
    if cursor is None and cursor_kind != "default":
        cursor = getattr(system_cursors, "DEFAULT", None)
    return cursor
