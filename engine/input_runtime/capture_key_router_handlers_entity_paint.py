from __future__ import annotations

from typing import Any

from engine.input_runtime.capture_runtime_focus_model import CaptureFocusSnapshot


def dispatch_entity_paint_action(
    window: Any,
    snapshot: CaptureFocusSnapshot,
    action_id: str,
) -> bool:
    if action_id == "capture.entity_paint.toggle":
        return _handle_entity_paint_toggle(window)
    if action_id.startswith("capture.entity_paint."):
        return _handle_entity_paint_action(window, action_id, snapshot)
    return False


def _set_editor_session_flag(window: Any, setter_name: str, value: bool) -> None:
    editor = getattr(window, "editor_controller", None)
    session = getattr(editor, "session", None) if editor is not None else None
    setter = getattr(session, setter_name, None) if session is not None else None
    if callable(setter):
        setter(bool(value))


def _handle_entity_paint_toggle(window: Any) -> bool:
    from engine.entity_paint_mode import EntityPaintState, load_prefab_infos  # noqa: PLC0415

    state = getattr(window, "entity_paint_state", None)
    if not isinstance(state, EntityPaintState):
        return False
    state.enabled = not bool(getattr(state, "enabled", False))
    if state.enabled and not getattr(state, "prefabs", ()):
        state.prefabs = load_prefab_infos()
        state.selected_index = 0
    if not state.enabled:
        state.persist_armed = False
    _set_editor_session_flag(window, "set_entity_paint_active", bool(getattr(state, "enabled", False)))
    return True


# ENTITY PAINT handlers

def _handle_entity_paint_action(window: Any, action_id: str, snapshot: CaptureFocusSnapshot) -> bool:
    from engine.entity_paint_mode import EntityPaintState  # noqa: PLC0415

    entity_state = getattr(window, "entity_paint_state", None)
    if not isinstance(entity_state, EntityPaintState):
        return False

    if action_id == "capture.entity_paint.toggle_persist_armed":
        entity_state.persist_armed = not bool(getattr(entity_state, "persist_armed", False))
        return True

    if action_id in ("capture.entity_paint.persist", "capture.entity_paint.validate"):
        validate_only = (action_id == "capture.entity_paint.validate")
        return _handle_entity_paint_persist(window, entity_state, validate_only=validate_only)

    # Handle slot selection/assignment
    if action_id.startswith("capture.entity_paint.slot_"):
        return _handle_entity_paint_slot_action(window, entity_state, action_id)

    # Handle hover nudge
    if action_id.startswith("capture.entity_paint.hover_nudge_"):
        return _handle_entity_paint_hover_nudge_action(window, entity_state, action_id)

    return False


def _handle_entity_paint_slot_action(window: Any, entity_state: Any, action_id: str) -> bool:
    """Handle entity paint (prefab) quick slot selection and assignment."""
    if not bool(getattr(entity_state, "enabled", False)):
        return False

    # Parse slot number from action_id like "capture.entity_paint.slot_select_3"
    try:
        parts = action_id.rsplit("_", 1)
        slot = int(parts[-1])
    except (ValueError, IndexError):
        return False

    if action_id.startswith("capture.entity_paint.slot_assign_"):
        # Alt+N: Assign current prefab to slot
        current_prefab = None
        try:
            from engine.entity_paint_mode import get_selected_prefab_id  # noqa: PLC0415
            current_prefab = get_selected_prefab_id(entity_state)
        except Exception:  # noqa: BLE001
            current_prefab = None
        if not isinstance(current_prefab, str) or not current_prefab.strip():
            print(f"PREFAB_SLOT_ASSIGN noop reason=empty slot={slot}")
            return True
        slots = getattr(window, "prefab_quick_slots", None)
        if not isinstance(slots, dict):
            slots = {}
            setattr(window, "prefab_quick_slots", slots)
        slots[int(slot)] = current_prefab.strip()
        print(f"PREFAB_SLOT_ASSIGN ok slot={slot} prefab={current_prefab.strip()}")
        return True

    if action_id.startswith("capture.entity_paint.slot_select_"):
        # N: Select prefab from slot
        slots = getattr(window, "prefab_quick_slots", None)
        prefab_id = None
        if isinstance(slots, dict):
            prefab_id = slots.get(int(slot))
        if not isinstance(prefab_id, str) or not prefab_id.strip():
            print(f"PREFAB_SLOT_SELECT noop reason=empty slot={slot}")
            return True
        try:
            from engine.entity_paint_mode import load_prefab_infos, select_prefab_id  # noqa: PLC0415
            if not getattr(entity_state, "prefabs", ()):
                entity_state.prefabs = load_prefab_infos()
            if select_prefab_id(entity_state, prefab_id.strip()):
                print(f"PREFAB_SLOT_SELECT ok slot={slot} prefab={prefab_id.strip()}")
            else:
                print(f"PREFAB_SLOT_SELECT noop reason=empty slot={slot}")
        except Exception:  # noqa: BLE001
            print(f"PREFAB_SLOT_SELECT noop reason=empty slot={slot}")
        return True

    return False


def _handle_entity_paint_hover_nudge_action(window: Any, entity_state: Any, action_id: str) -> bool:
    """Handle hover nudge for entity paint mode."""
    if not bool(getattr(entity_state, "enabled", False)):
        return False

    from engine.tooling_runtime.authoring_snippets import (  # noqa: PLC0415
        get_effective_hover_payload,
        get_scene_inspector_payload,
    )

    inspector_payload = get_scene_inspector_payload(window)
    effective_payload = get_effective_hover_payload(window, inspector_payload)
    hover_value = effective_payload.get("hover") if isinstance(effective_payload, dict) else None
    hover_payload = hover_value if isinstance(hover_value, dict) else {}
    hover_id = hover_payload.get("id")
    if not isinstance(hover_id, str) or not hover_id.strip():
        return False

    sc = getattr(window, "scene_controller", None)
    finder = getattr(sc, "debug_find_sprite_by_entity_id", None) if sc is not None else None
    sprite = finder(hover_id) if callable(finder) else None
    if sprite is None:
        return False

    fast = action_id.endswith("_fast")
    step = 8.0 if fast else 1.0

    dx = dy = 0.0
    if "nudge_left" in action_id:
        dx = -step
    elif "nudge_right" in action_id:
        dx = step
    elif "nudge_up" in action_id:
        dy = step
    elif "nudge_down" in action_id:
        dy = -step
    else:
        return False

    mover = getattr(sc, "debug_move_entity_by_id", None)
    if callable(mover):
        pusher = getattr(window, "push_undo_frame", None)
        if callable(pusher) and (dx or dy):
            pusher("entity_paint_nudge")
        if mover(hover_id, x=float(sprite.center_x) + dx, y=float(sprite.center_y) + dy):
            entity_state.moves += 1
            entity_state.last_snippet = (
                f"ENTITY_MOVE --id {hover_id} --x {float(sprite.center_x + dx):.1f} "
                f"--y {float(sprite.center_y + dy):.1f}"
            )
            marker = getattr(window, "mark_scene_dirty", None)
            if callable(marker):
                marker("entity_paint")
            return True
    return False


def _handle_entity_paint_persist(window: Any, entity_state: Any, *, validate_only: bool) -> bool:
    from engine.tooling_runtime.clipboard import try_copy_to_clipboard  # noqa: PLC0415
    from engine.tooling_runtime.entity_persist import persist_scene_payload, validate_scene_payload  # noqa: PLC0415

    sc = getattr(window, "scene_controller", None)
    authored_fn = getattr(sc, "get_authored_scene_payload", None) if sc is not None else None
    scene_payload = authored_fn() if callable(authored_fn) else (getattr(sc, "_loaded_scene_data", None) if sc is not None else None)
    scene_path = str(getattr(sc, "current_scene_path", "") or "").strip()

    if not isinstance(scene_payload, dict) or not scene_path:
        print("ENTITY_VALIDATE fail errors=1")
        entity_state.last_status = "ENTITY_VALIDATE fail errors=1"
        return True

    if validate_only:
        errors = validate_scene_payload(scene_payload)
        if errors:
            status = f"ENTITY_VALIDATE fail errors={len(errors)}"
        else:
            status = "ENTITY_VALIDATE ok errors=0"
        print(status)
        entity_state.last_status = status
        return True

    print(f"ENTITY_PAINT_APPLY adds={int(entity_state.adds)} removes={int(entity_state.removes)} moves={int(entity_state.moves)}")
    snippet = str(getattr(entity_state, "last_snippet", "") or "").strip()
    if snippet:
        try_copy_to_clipboard(snippet)

    if bool(getattr(entity_state, "persist_armed", False)):
        entity_persist_result = persist_scene_payload(scene_path, scene_payload, strict_no_overwrite=False)
        if entity_persist_result.ok:
            status = f"ENTITY_PERSIST ok path={entity_persist_result.path}"
            entity_state.adds = 0
            entity_state.removes = 0
            entity_state.moves = 0
        else:
            reason = ",".join(entity_persist_result.errors) if entity_persist_result.errors else "error"
            status = f"ENTITY_PERSIST fail reason={reason} path={entity_persist_result.path}"
        print(status)
        entity_state.last_status = status

    return True


__all__ = ["dispatch_entity_paint_action"]
