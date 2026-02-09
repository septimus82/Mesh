from __future__ import annotations

from typing import Any


def dispatch_tile_paint_action(window: Any, action_id: str) -> bool:
    if action_id == "capture.tile_paint.toggle":
        return _handle_tile_paint_toggle(window)
    if action_id.startswith("capture.tile_paint.slot_"):
        return _handle_tile_paint_slot_action(window, action_id)
    return False


def _handle_tile_paint_toggle(window: Any) -> bool:
    from engine.tile_paint_mode import TilePaintState  # noqa: PLC0415

    state = getattr(window, "tile_paint_state", None)
    if not isinstance(state, TilePaintState):
        return False

    state.enabled = not bool(getattr(state, "enabled", False))
    if state.enabled and not str(getattr(state, "layer_id", "") or "").strip():
        sc = getattr(window, "scene_controller", None)
        scene_payload = getattr(sc, "_loaded_scene_data", None) if sc is not None else None
        tilemap_value = scene_payload.get("tilemap") if isinstance(scene_payload, dict) else None
        tilemap_payload = tilemap_value if isinstance(tilemap_value, dict) else {}

        from engine.tile_paint_mode import cycle_layer_id  # noqa: PLC0415
        state.layer_id = cycle_layer_id(tile_layers=tilemap_payload.get("tile_layers") or [], current="", direction=1)
    return True


def _handle_tile_paint_slot_action(window: Any, action_id: str) -> bool:
    """Handle tile paint quick slot selection and assignment."""
    from engine.tile_paint_mode import TilePaintState  # noqa: PLC0415

    tile_state = getattr(window, "tile_paint_state", None)
    if not isinstance(tile_state, TilePaintState):
        return False
    if not bool(getattr(tile_state, "enabled", False)):
        return False

    # Parse slot number from action_id like "capture.tile_paint.slot_select_3"
    try:
        parts = action_id.rsplit("_", 1)
        slot = int(parts[-1])
    except (ValueError, IndexError):
        return False

    if action_id.startswith("capture.tile_paint.slot_assign_"):
        # Alt+N: Assign current tile to slot
        current = int(getattr(tile_state, "tile_id", 0) or 0)
        slots = getattr(window, "tile_quick_slots", None)
        if not isinstance(slots, dict):
            slots = {}
            setattr(window, "tile_quick_slots", slots)
        slots[int(slot)] = int(current)
        print(f"TILE_SLOT_ASSIGN ok slot={slot} tile={int(current)}")
        return True

    if action_id.startswith("capture.tile_paint.slot_select_"):
        # N: Select tile from slot
        slots = getattr(window, "tile_quick_slots", None)
        tile_id = None
        if isinstance(slots, dict):
            tile_id = slots.get(int(slot))
        if not isinstance(tile_id, int):
            print(f"TILE_SLOT_SELECT noop reason=empty slot={slot}")
            return True
        tile_state.tile_id = int(tile_id)
        print(f"TILE_SLOT_SELECT ok slot={slot} tile={int(tile_id)}")
        return True

    return False


__all__ = ["dispatch_tile_paint_action"]
