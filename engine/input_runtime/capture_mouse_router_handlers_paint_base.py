"""Base utilities for paint mouse handlers.

Shared helpers for tile paint, entity paint, and capture mode mouse handling.
"""
from __future__ import annotations

from typing import Any, Callable

import engine.optional_arcade as optional_arcade

from engine.input_runtime.capture_mouse_router_model import MouseEvent


_SWALLOW_ONCE_TAGS: set[str] = set()

def _log_swallow(tag: str, context: str, *, once: bool = True) -> None:
    if once and tag in _SWALLOW_ONCE_TAGS:
        return
    if once:
        _SWALLOW_ONCE_TAGS.add(tag)
    from engine.logging_tools import get_logger

    get_logger(__name__).debug("SWALLOW[%s] %s", tag, context, exc_info=True)


def get_tilemap_context(window: Any) -> tuple[Any, Any, tuple[int, int], tuple[int, int]] | None:
    """Get tilemap context: (scene_controller, tilemap_instance, map_size, tile_size).
    
    Returns None if tilemap is not available.
    """
    sc = getattr(window, "scene_controller", None)
    instance = getattr(sc, "tilemap_instance", None) if sc is not None else None
    if instance is None:
        return None
    map_w, map_h = getattr(instance, "map_size", (0, 0))
    tile_w, tile_h = getattr(instance, "tile_size", (0, 0))
    if not all(isinstance(v, int) for v in (map_w, map_h, tile_w, tile_h)):
        return None
    if int(map_w) <= 0 or int(map_h) <= 0:
        return None
    return sc, instance, (int(map_w), int(map_h)), (int(tile_w), int(tile_h))


def screen_to_world_safe(window: Any, x: float, y: float) -> tuple[float, float] | None:
    """Convert screen coordinates to world coordinates safely.
    
    Returns None if conversion fails.
    """
    try:
        world_x, world_y = window.screen_to_world(float(x), float(y))
        return (float(world_x), float(world_y))
    except Exception:  # noqa: BLE001
        return None


def is_left_click(event: MouseEvent) -> bool:
    """Check if event is a left mouse button click."""
    return int(event.button or 0) == int(optional_arcade.arcade.MOUSE_BUTTON_LEFT)


def is_right_click(event: MouseEvent) -> bool:
    """Check if event is a right mouse button click."""
    return int(event.button or 0) == int(optional_arcade.arcade.MOUSE_BUTTON_RIGHT)


def get_scroll_delta(event: MouseEvent) -> int:
    """Get scroll direction as -1, 0, or 1."""
    scroll_y = float(event.scroll_y)
    if scroll_y > 0:
        return 1
    if scroll_y < 0:
        return -1
    return 0


def has_modifier(event: MouseEvent, mod: int) -> bool:
    """Check if a modifier key is held."""
    return bool(event.modifiers & mod)


def has_shift(event: MouseEvent) -> bool:
    """Check if Shift is held."""
    return has_modifier(event, optional_arcade.arcade.key.MOD_SHIFT)


def has_ctrl(event: MouseEvent) -> bool:
    """Check if Ctrl is held."""
    return has_modifier(event, optional_arcade.arcade.key.MOD_CTRL)


def has_alt(event: MouseEvent) -> bool:
    """Check if Alt is held."""
    return has_modifier(event, optional_arcade.arcade.key.MOD_ALT)


def get_authoring_payloads(window: Any) -> list[dict]:
    """Get all authoring payloads from the scene controller."""
    sc = getattr(window, "scene_controller", None)
    if sc is None:
        return []
    
    iter_payloads: Callable[..., list[dict]] | None = getattr(sc, "_debug_iter_authoring_payloads", None)
    if iter_payloads is not None:
        try:
            result = iter_payloads()
            payloads = [p for p in result if isinstance(p, dict)]
            if payloads:
                return payloads
        except Exception:  # noqa: BLE001
            _log_swallow("CAPT-001", "engine/input_runtime/capture_mouse_router_handlers_paint_base.py pass-only blanket swallow")
            pass
    
    # Fallback to loaded scene data
    scene_data = getattr(sc, "_loaded_scene_data", None)
    if isinstance(scene_data, dict):
        return [scene_data]
    return []


__all__ = [
    "get_tilemap_context",
    "screen_to_world_safe",
    "is_left_click",
    "is_right_click",
    "get_scroll_delta",
    "has_modifier",
    "has_shift",
    "has_ctrl",
    "has_alt",
    "get_authoring_payloads",
]
