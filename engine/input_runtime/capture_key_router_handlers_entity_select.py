from __future__ import annotations

from typing import Any

from engine.input_runtime.capture_runtime_focus_model import CaptureFocusSnapshot


def dispatch_entity_select_action(
    window: Any,
    snapshot: CaptureFocusSnapshot,
    action_id: str,
) -> bool:
    if action_id.startswith("capture.entity_select."):
        return _handle_entity_select_action(window, action_id, snapshot)
    return False


def _handle_entity_select_action(window: Any, action_id: str, snapshot: CaptureFocusSnapshot) -> bool:
    from engine.entity_select_mode import (  # noqa: PLC0415
        EntitySelectState,
        other_authoring_modes_active,
        selection_sorted_unique,
    )

    if other_authoring_modes_active(window):
        return False

    state = getattr(window, "entity_select_state", None)
    if not isinstance(state, EntitySelectState):
        return False

    selected_ids = selection_sorted_unique(list(getattr(state, "selected_ids", []) or []))
    if not selected_ids and action_id not in ("capture.entity_select.paste",):
        return False

    sc = getattr(window, "scene_controller", None)

    if action_id == "capture.entity_select.delete":
        return _handle_entity_select_delete(window, state, selected_ids, sc)

    if action_id.startswith("capture.entity_select.nudge_"):
        return _handle_entity_select_nudge(window, state, selected_ids, action_id, sc)

    if action_id == "capture.entity_select.duplicate":
        return _handle_entity_select_duplicate(window, state, selected_ids, sc)

    if action_id == "capture.entity_select.copy":
        return _handle_entity_select_copy(window, state, selected_ids, sc)

    if action_id == "capture.entity_select.paste":
        return _handle_entity_select_paste(window, state, sc)

    if action_id in ("capture.entity_select.rotate", "capture.entity_select.flip_x", "capture.entity_select.flip_y"):
        return _handle_entity_select_transform(window, state, selected_ids, action_id, sc)

    return False


def _handle_entity_select_delete(window: Any, state: Any, selected_ids: list[str], sc: Any) -> bool:
    if not selected_ids:
        return False

    # Use the singular remove method if available
    deleter = getattr(sc, "debug_remove_entity_by_id", None) if sc is not None else None
    if not callable(deleter):
        print("ENTITY_DELETE noop reason=no_deleter")
        return True

    pusher = getattr(window, "push_undo_frame", None)
    if callable(pusher):
        pusher("entity_select_delete")

    # Delete entities one by one
    count = 0
    for entity_id in selected_ids:
        if deleter(entity_id):
            count += 1

    from engine.entity_select_mode import clear_drag, set_selection  # noqa: PLC0415

    # Always clear selection and drag state after delete attempt
    clear_drag(state)
    set_selection(window, state, [])

    if count <= 0:
        print("ENTITY_DELETE noop reason=only_player")
        return True

    marker = getattr(window, "mark_scene_dirty", None)
    if callable(marker):
        marker("entity_select_multi" if len(selected_ids) > 1 else "entity_select_delete")
    window.last_delete_count = int(count)
    window.last_delete_counter = int(getattr(window, "scene_dirty_counter", 0) or 0)

    print(f"ENTITY_DELETE ok count={count}")
    return True


def _handle_entity_select_nudge(window: Any, state: Any, selected_ids: list[str], action_id: str, sc: Any) -> bool:
    mover = getattr(sc, "debug_move_entity_by_id", None) if sc is not None else None
    finder = getattr(sc, "debug_find_sprite_by_entity_id", None) if sc is not None else None
    if not callable(mover) or not callable(finder):
        return False

    large = "large" in action_id
    step = 8.0 if large else 1.0
    dx = dy = 0.0
    if "left" in action_id:
        dx = -step
    elif "right" in action_id:
        dx = step
    elif "up" in action_id:
        dy = step
    elif "down" in action_id:
        dy = -step

    pusher = getattr(window, "push_undo_frame", None)
    if callable(pusher) and (dx or dy):
        pusher("entity_select_nudge")

    moved_any = False
    for entity_id in selected_ids:
        sprite = finder(entity_id)
        if sprite is None:
            continue
        moved_any = bool(mover(entity_id, x=float(sprite.center_x) + dx, y=float(sprite.center_y) + dy)) or moved_any

    if moved_any:
        marker = getattr(window, "mark_scene_dirty", None)
        if callable(marker):
            marker("entity_select_multi")
    return True


def _handle_entity_select_duplicate(window: Any, state: Any, selected_ids: list[str], sc: Any) -> bool:
    from engine.entity_select_mode import get_duplicate_offset, set_selection  # noqa: PLC0415
    from engine.input_runtime.capture_io import _recent_push_many  # noqa: PLC0415

    duplicator = getattr(sc, "debug_duplicate_entities_by_ids", None) if sc is not None else None
    if not callable(duplicator):
        print("ENTITY_DUPLICATE noop (no duplicator)")
        return True

    pusher = getattr(window, "push_undo_frame", None)
    if callable(pusher):
        pusher("entity_select_duplicate")

    dx, dy = get_duplicate_offset(window)
    mapping = duplicator(selected_ids, dx=float(dx), dy=float(dy))
    new_ids = sorted({str(v).strip() for v in (mapping or {}).values() if isinstance(v, str) and str(v).strip()})
    if not new_ids:
        print("ENTITY_DUPLICATE noop (no matches)")
        return True

    old_primary = str(getattr(state, "primary_id", "") or "").strip()
    new_primary = mapping.get(old_primary) if isinstance(mapping, dict) else None
    if not isinstance(new_primary, str) or not new_primary.strip():
        new_primary = new_ids[0]

    set_selection(window, state, new_ids, primary_id=new_primary)

    marker = getattr(window, "mark_scene_dirty", None)
    if callable(marker):
        marker("entity_select_duplicate")
    window.last_duplicate_count = int(len(new_ids))
    window.last_duplicate_primary = str(new_primary)
    window.last_duplicate_counter = int(getattr(window, "scene_dirty_counter", 0) or 0)

    authored_fn = getattr(sc, "get_authored_scene_payload", None) if sc is not None else None
    authored_payload = authored_fn() if callable(authored_fn) else None
    if isinstance(authored_payload, dict):
        ents = authored_payload.get("entities")
        if isinstance(ents, list):
            dup_entities_by_id = {str(e.get("id")): e for e in ents if isinstance(e, dict) and isinstance(e.get("id"), str)}
            dup_prefab_ids = []
            for eid in new_ids:
                ent = dup_entities_by_id.get(eid)
                pid = ent.get("prefab_id") if isinstance(ent, dict) else None
                if isinstance(pid, str) and pid.strip():
                    dup_prefab_ids.append(pid.strip())
            _recent_push_many(window, attr="prefab_recent", values=dup_prefab_ids, max_items=12)

    print(f"ENTITY_DUPLICATE ok count={len(new_ids)} dx={float(dx):.1f} dy={float(dy):.1f}")
    return True


def _handle_entity_select_copy(window: Any, state: Any, selected_ids: list[str], sc: Any) -> bool:
    copier = getattr(sc, "debug_copy_entities_by_ids", None) if sc is not None else None
    if not callable(copier):
        print("ENTITY_COPY noop reason=no_selection")
        return True

    primary_id = str(getattr(state, "primary_id", "") or "").strip() or (selected_ids[0] if selected_ids else "")
    clip = copier(selected_ids, primary_id=primary_id)
    entities = clip.get("entities") if isinstance(clip, dict) else None
    if not isinstance(entities, list) or not entities:
        print("ENTITY_COPY noop reason=only_player")
        return True

    setattr(window, "entity_clipboard", clip)
    print(f"ENTITY_COPY ok count={len(entities)}")
    return True


def _handle_entity_select_paste(window: Any, state: Any, sc: Any) -> bool:
    from engine.entity_select_mode import set_selection  # noqa: PLC0415
    from engine.input_runtime.capture_io import _recent_push_many  # noqa: PLC0415

    clip = getattr(window, "entity_clipboard", None)
    entities = clip.get("entities") if isinstance(clip, dict) else None
    if not isinstance(entities, list) or not entities:
        print("ENTITY_PASTE noop reason=empty_clipboard")
        return True

    paster = getattr(sc, "debug_paste_entities_from_clipboard", None) if sc is not None else None
    if not callable(paster):
        print("ENTITY_PASTE noop reason=empty_clipboard")
        return True

    anchor_x = anchor_y = None
    input_ctrl = getattr(window, "input_controller", None)
    mx = getattr(input_ctrl, "mouse_x", None) if input_ctrl is not None else None
    my = getattr(input_ctrl, "mouse_y", None) if input_ctrl is not None else None
    to_world = getattr(window, "screen_to_world", None)
    if callable(to_world) and isinstance(mx, (int, float)) and isinstance(my, (int, float)):
        try:
            anchor_x, anchor_y = to_world(float(mx), float(my))
        except Exception:  # noqa: BLE001  # REASON: screen-to-world conversion failures should fall back to non-cursor selection anchors
            anchor_x, anchor_y = None, None
    if not (isinstance(anchor_x, (int, float)) and isinstance(anchor_y, (int, float))):
        finder = getattr(sc, "_find_player_sprite", None) if sc is not None else None
        try:
            player = finder() if callable(finder) else None
        except Exception:  # noqa: BLE001  # REASON: player anchor lookup is optional and should fall back to no player selection anchor
            player = None
        if player is not None:
            anchor_x, anchor_y = float(player.center_x), float(player.center_y)
        else:
            anchor_x, anchor_y = 0.0, 0.0

    pusher = getattr(window, "push_undo_frame", None)
    if callable(pusher):
        pusher("entity_select_paste")

    pasted_ids, pasted_primary = paster(
        clip,
        anchor_x=float(anchor_x),
        anchor_y=float(anchor_y),
        snap_to_tile=bool(getattr(window, "entity_snap_to_tile", False)),
    )
    if not pasted_ids:
        print("ENTITY_PASTE noop reason=empty_clipboard")
        return True

    if state is not None:
        set_selection(window, state, pasted_ids, primary_id=pasted_primary)

    marker = getattr(window, "mark_scene_dirty", None)
    if callable(marker):
        marker("entity_select_paste")

    authored_fn = getattr(sc, "get_authored_scene_payload", None) if sc is not None else None
    authored_payload = authored_fn() if callable(authored_fn) else None
    if isinstance(authored_payload, dict):
        ents = authored_payload.get("entities")
        if isinstance(ents, list):
            pasted_entities_by_id = {str(e.get("id")): e for e in ents if isinstance(e, dict) and isinstance(e.get("id"), str)}
            pasted_prefab_ids = []
            for eid in pasted_ids:
                ent = pasted_entities_by_id.get(eid)
                pid = ent.get("prefab_id") if isinstance(ent, dict) else None
                if isinstance(pid, str) and pid.strip():
                    pasted_prefab_ids.append(pid.strip())
            _recent_push_many(window, attr="prefab_recent", values=pasted_prefab_ids, max_items=12)

    print(f"ENTITY_PASTE ok count={len(pasted_ids)} primary={pasted_primary}")
    return True


def _handle_entity_select_transform(window: Any, state: Any, selected_ids: list[str], action_id: str, sc: Any) -> bool:
    transformer = getattr(sc, "debug_transform_entities_by_ids", None) if sc is not None else None
    if not callable(transformer):
        print("ENTITY_TRANSFORM noop reason=no_selection")
        return True

    if action_id == "capture.entity_select.rotate":
        op = "rotate_cw_90"
        ok_prefix = "ENTITY_ROTATE"
        action = "rotate"
    elif action_id == "capture.entity_select.flip_x":
        op = "flip_x"
        ok_prefix = "ENTITY_FLIP_X"
        action = "flip_x"
    else:
        op = "flip_y"
        ok_prefix = "ENTITY_FLIP_Y"
        action = "flip_y"

    pusher = getattr(window, "push_undo_frame", None)
    if callable(pusher):
        pusher("entity_select_transform")

    count = int(transformer(
        selected_ids,
        op=op,
        snap_to_tile=bool(getattr(window, "entity_snap_to_tile", False)),
    ) or 0)
    if count <= 0:
        print("ENTITY_TRANSFORM noop reason=only_player")
        return True

    marker = getattr(window, "mark_scene_dirty", None)
    if callable(marker):
        marker("entity_select_transform")
    window.last_transform_action = str(action)
    window.last_transform_count = int(count)
    window.last_transform_counter = int(getattr(window, "scene_dirty_counter", 0) or 0)

    print(f"{ok_prefix} ok count={count}")
    return True


__all__ = ["dispatch_entity_select_action"]
