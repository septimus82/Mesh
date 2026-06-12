"""Mouse handling for tile_paint scope."""
from __future__ import annotations

from typing import Any, Callable, cast

import engine.optional_arcade as optional_arcade
from engine.input_runtime.capture_mouse_router_handlers_modal_base import (
    maybe_handle_editor_mouse_press,
    maybe_handle_editor_mouse_release,
)
from engine.input_runtime.capture_mouse_router_model import MouseEvent


def dispatch_tile_paint_mouse(controller: Any, event: MouseEvent, action_id: str) -> bool:
    """Dispatch mouse event for tile_paint scope."""
    window = controller.window

    if action_id == "mouse.tile_paint.press":
        if maybe_handle_editor_mouse_press(window, event):
            return True
        return _handle_tile_paint_mouse_press(window, event)

    if action_id == "mouse.tile_paint.release":
        if maybe_handle_editor_mouse_release(window, event):
            return True
        return _handle_tile_paint_mouse_release(window, event)

    if action_id == "mouse.tile_paint.scroll":
        return _handle_tile_paint_mouse_scroll(window, event)

    return False


def _handle_tile_paint_mouse_press(window: Any, event: MouseEvent) -> bool:
    from engine.tile_paint_mode import TilePaintState  # noqa: PLC0415

    state = getattr(window, "tile_paint_state", None)
    if not (
        bool(getattr(window, "show_debug", False))
        and isinstance(state, TilePaintState)
        and bool(getattr(state, "enabled", False))
    ):
        return False
    if int(event.button or 0) not in (
        int(optional_arcade.arcade.MOUSE_BUTTON_LEFT),
        int(optional_arcade.arcade.MOUSE_BUTTON_RIGHT),
    ):
        return True
    sc = getattr(window, "scene_controller", None)
    instance = getattr(sc, "tilemap_instance", None) if sc is not None else None
    if instance is None:
        return True
    map_w, map_h = getattr(instance, "map_size", (0, 0))
    tile_w, tile_h = getattr(instance, "tile_size", (0, 0))
    try:
        world_x, world_y = window.screen_to_world(float(event.x), float(event.y))
    except Exception:  # noqa: BLE001  # REASON: screen-to-world conversion failures should fall back to no tile-paint click handling
        return True
    from engine.tile_paint_mode import compute_tile_paint_tool, peek_tile_value, world_to_tile  # noqa: PLC0415

    hit = world_to_tile(
        map_width=int(map_w),
        map_height=int(map_h),
        tile_width=int(tile_w),
        tile_height=int(tile_h),
        world_x=float(world_x),
        world_y=float(world_y),
    )
    if hit is None:
        return True

    tool = compute_tile_paint_tool(
        shift=bool(event.modifiers & optional_arcade.arcade.key.MOD_SHIFT),
        ctrl=bool(event.modifiers & optional_arcade.arcade.key.MOD_CTRL),
        alt=bool(event.modifiers & optional_arcade.arcade.key.MOD_ALT),
    )
    if tool == "pick":
        payloads: list[dict] = []
        _iter_fn = getattr(sc, "_debug_iter_authoring_payloads", None) if sc is not None else None
        if _iter_fn is not None:
            try:
                payloads = [p for p in cast(Callable[..., list[dict]], _iter_fn)() if isinstance(p, dict)]
            except Exception:  # noqa: BLE001  # REASON: authored scene payload queries are optional and should fall back to loaded scene payloads only
                payloads = []
        if not payloads and sc is not None and isinstance(getattr(sc, "_loaded_scene_data", None), dict):
            payloads = [sc._loaded_scene_data]
        if not payloads:
            return True
        layer_id = str(getattr(state, "layer_id", "") or "").strip()
        if not layer_id:
            return True
        for payload in payloads:
            picked = peek_tile_value(
                payload,
                layer_id=layer_id,
                tx=int(hit[0]),
                ty=int(hit[1]),
                map_width=int(map_w),
                map_height=int(map_h),
            )
            if picked is not None:
                state.tile_id = int(picked)
                from engine.input_runtime.capture_io import _recent_push_int  # noqa: PLC0415

                _recent_push_int(window, attr="tile_recent", value=int(picked), max_items=12)
                print(f"TILE_PICK ok tile={int(picked)} layer={layer_id}")
                return True
        return True

    state.stroke_active = True
    state.stroke_tool = tool
    state.stroke_button = int(event.button or 0)
    state.stroke_anchor = (int(hit[0]), int(hit[1]))
    state.stroke_last_hit = (int(hit[0]), int(hit[1]))
    state.stroke_coords.clear()
    if str(tool) == "brush":
        state.stroke_coords.add((int(hit[0]), int(hit[1])))
    return True


def _handle_tile_paint_mouse_release(window: Any, event: MouseEvent) -> bool:
    from engine.tile_paint_mode import TilePaintState  # noqa: PLC0415

    state = getattr(window, "tile_paint_state", None)
    if not (
        bool(getattr(window, "show_debug", False))
        and isinstance(state, TilePaintState)
        and bool(getattr(state, "enabled", False))
        and bool(getattr(state, "stroke_active", False))
    ):
        return False
    if int(event.button or 0) != int(getattr(state, "stroke_button", 0) or 0):
        return True
    from engine.tile_paint_mode import (  # noqa: PLC0415
        apply_erase,
        apply_paint,
        iter_sorted_tile_coords,
        line_coords_4_connected,
        peek_tile_value,
        rect_fill_coords,
        rect_outline_coords,
    )

    sc = getattr(window, "scene_controller", None)
    instance = getattr(sc, "tilemap_instance", None) if sc is not None else None
    payloads: list[dict] = []
    _iter_fn2 = getattr(sc, "_debug_iter_authoring_payloads", None) if sc is not None else None
    if _iter_fn2 is not None:
        try:
            payloads = [p for p in cast(Callable[..., list[dict]], _iter_fn2)() if isinstance(p, dict)]
        except Exception:  # noqa: BLE001  # REASON: authored scene payload queries are optional and should fall back to loaded scene payloads only
            payloads = []
    if not payloads and sc is not None and isinstance(getattr(sc, "_loaded_scene_data", None), dict):
        payloads = [sc._loaded_scene_data]

    tool = str(getattr(state, "stroke_tool", "") or "brush")
    layer_id = str(getattr(state, "layer_id", "") or "").strip()
    desired_tile = 0 if int(event.button or 0) == int(optional_arcade.arcade.MOUSE_BUTTON_RIGHT) else int(getattr(state, "tile_id", 0) or 0)

    if not payloads or instance is None:
        print("TILE_STROKE noop reason=no_tilemap")
        state.stroke_active = False
        state.stroke_anchor = None
        state.stroke_last_hit = None
        state.stroke_coords.clear()
        return True

    map_w, map_h = getattr(instance, "map_size", (0, 0))
    tile_w, tile_h = getattr(instance, "tile_size", (0, 0))
    if not all(isinstance(v, int) for v in (map_w, map_h, tile_w, tile_h)) or int(map_w) <= 0 or int(map_h) <= 0:
        print("TILE_STROKE noop reason=dims_missing")
        state.stroke_active = False
        state.stroke_anchor = None
        state.stroke_last_hit = None
        state.stroke_coords.clear()
        return True

    anchor = getattr(state, "stroke_anchor", None)
    end = getattr(state, "stroke_last_hit", None)
    if not (isinstance(anchor, tuple) and len(anchor) == 2 and isinstance(end, tuple) and len(end) == 2 and layer_id):
        print("TILE_STROKE noop reason=no_changes")
        state.stroke_active = False
        state.stroke_anchor = None
        state.stroke_last_hit = None
        state.stroke_coords.clear()
        return True

    ax, ay = int(anchor[0]), int(anchor[1])
    ex, ey = int(end[0]), int(end[1])
    if tool == "brush":
        coords = set(getattr(state, "stroke_coords", set()) or set())
        if not coords:
            coords = {(ax, ay)}
    elif tool == "line":
        coords = set(line_coords_4_connected(x0=ax, y0=ay, x1=ex, y1=ey))
    elif tool == "rect_fill":
        coords = rect_fill_coords(x0=ax, y0=ay, x1=ex, y1=ey)
    else:
        coords = rect_outline_coords(x0=ax, y0=ay, x1=ex, y1=ey)

    coords_sorted = iter_sorted_tile_coords(coords)
    if not coords_sorted:
        print("TILE_STROKE noop reason=no_changes")
        state.stroke_active = False
        state.stroke_anchor = None
        state.stroke_last_hit = None
        state.stroke_coords.clear()
        return True

    will_change = False
    for cx, cy in coords_sorted:
        for payload in payloads:
            before = peek_tile_value(payload, layer_id=layer_id, tx=int(cx), ty=int(cy), map_width=int(map_w), map_height=int(map_h))
            if before is None or int(before) != int(desired_tile):
                will_change = True
                break
        if will_change:
            break

    if not will_change:
        print("TILE_STROKE noop reason=no_changes")
        state.stroke_active = False
        state.stroke_anchor = None
        state.stroke_last_hit = None
        state.stroke_coords.clear()
        return True

    pusher = getattr(window, "push_undo_frame", None)
    if callable(pusher):
        pusher("tile_paint_drag")

    changed_coords: set[tuple[int, int]] = set()
    try:
        for cx, cy in coords_sorted:
            changed_any = False
            for payload in payloads:
                if int(event.button or 0) == int(optional_arcade.arcade.MOUSE_BUTTON_RIGHT):
                    changed_any = apply_erase(
                        payload,
                        layer_id=layer_id,
                        tx=int(cx),
                        ty=int(cy),
                        map_width=int(map_w),
                        map_height=int(map_h),
                    ) or changed_any
                else:
                    changed_any = (
                        apply_paint(
                            payload,
                            layer_id=layer_id,
                            tx=int(cx),
                            ty=int(cy),
                            tile_id=int(desired_tile),
                            map_width=int(map_w),
                            map_height=int(map_h),
                        )
                        or changed_any
                    )
            if changed_any:
                changed_coords.add((int(cx), int(cy)))
    except Exception:  # noqa: BLE001  # REASON: stroke apply failures should clear transient tile-paint drag state without blocking later input handling
        state.stroke_active = False
        state.stroke_anchor = None
        state.stroke_last_hit = None
        state.stroke_coords.clear()
        return True

    if not changed_coords:
        print("TILE_STROKE noop reason=no_changes")
    else:
        refresh = getattr(sc, "refresh_tilemap_layers", None)
        if callable(refresh):
            refresh()
        marker = getattr(window, "mark_scene_dirty", None)
        if callable(marker):
            marker("tile_paint_drag")
        from engine.input_runtime.capture_io import _recent_push_int  # noqa: PLC0415

        _recent_push_int(window, attr="tile_recent", value=int(desired_tile), max_items=12)
        print(f"TILE_STROKE ok tool={tool} count={len(changed_coords)} layer={layer_id} tile={int(desired_tile)}")

    state.stroke_active = False
    state.stroke_anchor = None
    state.stroke_last_hit = None
    state.stroke_coords.clear()
    return True


def _handle_tile_paint_mouse_scroll(window: Any, event: MouseEvent) -> bool:
    from engine.tile_paint_mode import TilePaintState  # noqa: PLC0415

    state = getattr(window, "tile_paint_state", None)
    if not (
        bool(getattr(window, "show_debug", False))
        and isinstance(state, TilePaintState)
        and bool(getattr(state, "enabled", False))
    ):
        return False

    delta = int(1 if float(event.scroll_y) > 0 else (-1 if float(event.scroll_y) < 0 else 0))
    if delta == 0:
        return True

    if event.modifiers & optional_arcade.arcade.key.MOD_SHIFT:
        from engine.tile_paint_mode import cycle_layer_id  # noqa: PLC0415

        sc = getattr(window, "scene_controller", None)
        scene_payload = getattr(sc, "_loaded_scene_data", None) if sc is not None else None
        tilemap_value = scene_payload.get("tilemap") if isinstance(scene_payload, dict) else None
        tilemap_payload: dict[str, Any] = tilemap_value if isinstance(tilemap_value, dict) else {}
        state.layer_id = cycle_layer_id(
            tile_layers=tilemap_payload.get("tile_layers") or [],
            current=str(getattr(state, "layer_id", "")),
            direction=delta,
        )
        return True

    current = int(getattr(state, "tile_id", 0))
    state.tile_id = max(0, min(9999, current + delta))
    return True


__all__ = ["dispatch_tile_paint_mouse"]
