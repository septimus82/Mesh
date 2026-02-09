"""Mouse handling for capture_mode scope."""
from __future__ import annotations

from typing import Any, cast

import engine.optional_arcade as optional_arcade

from engine.input_runtime.capture_mouse_router_model import MouseEvent
from engine.input_runtime.capture_mouse_router_handlers_modal_base import (
    maybe_handle_editor_mouse_press,
    maybe_handle_editor_mouse_release,
)


def dispatch_capture_mode_mouse(controller: Any, event: MouseEvent, action_id: str) -> bool:
    """Dispatch mouse event for capture_mode scope."""
    window = controller.window

    if action_id == "mouse.capture_mode.press":
        if maybe_handle_editor_mouse_press(window, event):
            return True
        return _handle_capture_mode_mouse_press(window, event)

    if action_id == "mouse.capture_mode.release":
        if maybe_handle_editor_mouse_release(window, event):
            return True
        return _handle_capture_mode_mouse_release(window, event)

    if action_id == "mouse.capture_mode.scroll":
        return _handle_capture_mode_mouse_scroll(window, event)

    return False


def _handle_capture_mode_mouse_press(window: Any, event: MouseEvent) -> bool:
    from engine.capture_mode import CaptureState  # noqa: PLC0415

    capture_state = getattr(window, "capture_state", None)
    if not (
        isinstance(capture_state, CaptureState)
        and bool(getattr(window, "show_debug", False))
        and bool(getattr(capture_state, "enabled", False))
    ):
        return False
    if int(event.button or 0) != int(optional_arcade.arcade.MOUSE_BUTTON_LEFT):
        return True
    sc = getattr(window, "scene_controller", None)
    instance = getattr(sc, "tilemap_instance", None) if sc is not None else None
    if instance is None:
        return True
    map_w, map_h = getattr(instance, "map_size", (0, 0))
    tile_w, tile_h = getattr(instance, "tile_size", (0, 0))
    try:
        world_x, world_y = window.screen_to_world(float(event.x), float(event.y))
    except Exception:  # noqa: BLE001
        return True
    from engine.tile_paint_mode import world_to_tile  # noqa: PLC0415

    hit = world_to_tile(
        map_width=int(map_w),
        map_height=int(map_h),
        tile_width=int(tile_w),
        tile_height=int(tile_h),
        world_x=float(world_x),
        world_y=float(world_y),
    )
    if hit is not None:
        capture_state.drag_anchor = (int(hit[0]), int(hit[1]))
        from engine.capture_mode import normalize_rect  # noqa: PLC0415

        capture_state.rect = normalize_rect(int(hit[0]), int(hit[1]), int(hit[0]), int(hit[1]))
    return True


def _handle_capture_mode_mouse_release(window: Any, event: MouseEvent) -> bool:
    from engine.capture_mode import CaptureState  # noqa: PLC0415

    capture_state = getattr(window, "capture_state", None)
    if not (
        isinstance(capture_state, CaptureState)
        and bool(getattr(window, "show_debug", False))
        and bool(getattr(capture_state, "enabled", False))
    ):
        return False
    if int(event.button or 0) == int(optional_arcade.arcade.MOUSE_BUTTON_LEFT):
        capture_state.drag_anchor = None
    return True


def _handle_capture_mode_mouse_scroll(window: Any, event: MouseEvent) -> bool:
    from engine.capture_mode import CaptureState  # noqa: PLC0415

    capture_state = getattr(window, "capture_state", None)
    if not (
        isinstance(capture_state, CaptureState)
        and bool(getattr(window, "show_debug", False))
        and bool(getattr(capture_state, "enabled", False))
    ):
        return False
    delta = int(1 if float(event.scroll_y) > 0 else (-1 if float(event.scroll_y) < 0 else 0))
    if delta == 0:
        return True

    sc = getattr(window, "scene_controller", None)
    payload = getattr(sc, "_loaded_scene_data", None) if sc is not None else None
    if not isinstance(payload, dict):
        return True

    if event.modifiers & optional_arcade.arcade.key.MOD_CTRL:
        from engine.capture_mode import iter_layer_ids_sorted_by_z_id  # noqa: PLC0415

        ids = iter_layer_ids_sorted_by_z_id(payload)
        if ids:
            cur = str(getattr(capture_state, "layer_id", "") or "").strip()
            if cur not in ids:
                capture_state.layer_id = ids[0]
            else:
                idx = ids.index(cur)
                capture_state.layer_id = ids[(idx + delta) % len(ids)]
        return True

    mode = str(getattr(capture_state, "mode", "stamp")).strip().lower()
    if mode != "brush":
        return True

    from engine.capture_mode import BrushFilterMode  # noqa: PLC0415

    current_mode_raw = str(getattr(capture_state, "brush_filter_mode", "nonzero")).strip().lower()
    mode_order: list[BrushFilterMode] = ["nonzero", "tile", "all"]
    current_mode: BrushFilterMode = cast(
        BrushFilterMode,
        current_mode_raw if current_mode_raw in mode_order else "nonzero",
    )

    idx = mode_order.index(current_mode)
    next_mode: BrushFilterMode = mode_order[(idx + delta) % len(mode_order)]
    capture_state.brush_filter_mode = next_mode
    if next_mode == "tile":
        layer_id = str(getattr(capture_state, "layer_id", "") or "").strip()
        instance = getattr(sc, "tilemap_instance", None) if sc is not None else None
        if layer_id and instance is not None:
            map_w, map_h = getattr(instance, "map_size", (0, 0))
            tile_w, tile_h = getattr(instance, "tile_size", (0, 0))
            try:
                world_x, world_y = window.screen_to_world(float(event.x), float(event.y))
            except Exception:  # noqa: BLE001
                world_x, world_y = None, None
            if isinstance(world_x, (int, float)) and isinstance(world_y, (int, float)):
                from engine.tile_paint_mode import world_to_tile  # noqa: PLC0415

                hit = world_to_tile(
                    map_width=int(map_w),
                    map_height=int(map_h),
                    tile_width=int(tile_w),
                    tile_height=int(tile_h),
                    world_x=float(world_x),
                    world_y=float(world_y),
                )
                if hit is not None:
                    tx, ty = hit
                    tilemap = payload.get("tilemap") if isinstance(payload.get("tilemap"), dict) else None
                    raw_layers = tilemap.get("tile_layers") if isinstance(tilemap, dict) else None
                    entry = (
                        next((e for e in raw_layers if isinstance(e, dict) and e.get("id") == layer_id), None)
                        if isinstance(raw_layers, list)
                        else None
                    )
                    tiles = entry.get("tiles") if isinstance(entry, dict) else None
                    if (
                        isinstance(tiles, list)
                        and len(tiles) == int(map_w) * int(map_h)
                        and all(isinstance(v, int) for v in tiles)
                    ):
                        capture_state.brush_filter_value = int(tiles[int(ty) * int(map_w) + int(tx)])
    return True


__all__ = ["dispatch_capture_mode_mouse"]
