from __future__ import annotations

from typing import Any

from engine.input_runtime.capture_runtime_focus_model import CaptureFocusSnapshot


def dispatch_palette_action(
    window: Any,
    snapshot: CaptureFocusSnapshot,
    action_id: str,
) -> bool:
    if action_id.startswith("capture.palette_mode."):
        return _handle_palette_mode_action(window, action_id, snapshot)
    if action_id.startswith("capture.capture_mode."):
        return _handle_capture_mode_action(window, action_id, snapshot)
    return False


def _set_editor_session_flag(window: Any, setter_name: str, value: bool) -> None:
    editor = getattr(window, "editor_controller", None)
    session = getattr(editor, "session", None) if editor is not None else None
    setter = getattr(session, setter_name, None) if session is not None else None
    if callable(setter):
        setter(bool(value))


# PALETTE MODE handlers

def _handle_palette_mode_action(window: Any, action_id: str, snapshot: CaptureFocusSnapshot) -> bool:
    from engine.palette_mode import get_state, toggle_mode, move_selection, toggle_preview, apply_at  # noqa: PLC0415

    if action_id == "capture.palette_mode.toggle_mode":
        toggle_mode()
        return True
    if action_id == "capture.palette_mode.up":
        move_selection(-1)
        return True
    if action_id == "capture.palette_mode.down":
        move_selection(1)
        return True
    if action_id == "capture.palette_mode.toggle_preview":
        toggle_preview()
        return True
    if action_id == "capture.palette_mode.block_gameplay":
        return True
    if action_id in ("capture.palette_mode.apply", "capture.palette_mode.apply_last"):
        palette_state = get_state()
        cam_x = getattr(window.camera_controller, "camera_x", 0)
        cam_y = getattr(window.camera_controller, "camera_y", 0)
        mx = getattr(window.input_controller, "mouse_x", 0)
        my = getattr(window.input_controller, "mouse_y", 0)
        world_x = cam_x + mx
        world_y = cam_y + my
        tx = int(world_x // 32)
        ty = int(world_y // 32)

        sc = getattr(window, "scene_controller", None)
        scene_payload = getattr(sc, "current_scene_data", None) if sc is not None else None
        runtime_payload = getattr(sc, "_loaded_scene_data", None) if sc is not None else None

        payloads: list[dict] = []
        for candidate in (scene_payload, runtime_payload):
            if isinstance(candidate, dict) and candidate not in payloads:
                payloads.append(candidate)

        if payloads:
            pusher = getattr(window, "push_undo_frame", None)
            if callable(pusher):
                pusher("palette_apply")

            if action_id == "capture.palette_mode.apply_last":
                from engine.palette_mode import apply_last_saved_at  # noqa: PLC0415
                applied_any = False
                for payload in payloads:
                    applied_any = apply_last_saved_at(payload, tx, ty) or applied_any
                kind = str(getattr(palette_state, "last_saved_type", "") or "").strip()
            else:
                applied_any = False
                for payload in payloads:
                    applied_any = bool(apply_at(payload, tx, ty)) or applied_any
                selected_item = getattr(palette_state, "selected_item", None)
                kind = str(getattr(selected_item, "type", "") or "").strip()

            if applied_any:
                marker = getattr(window, "mark_scene_dirty", None)
                if callable(marker):
                    marker("palette_stamp" if kind == "stamp" else "palette_brush")
                refresh = getattr(sc, "refresh_tilemap_layers", None) if sc is not None else None
                if callable(refresh):
                    refresh()
        return True

    return False


# CAPTURE MODE handlers

def _handle_capture_mode_action(window: Any, action_id: str, snapshot: CaptureFocusSnapshot) -> bool:
    from engine.capture_mode import CaptureState  # noqa: PLC0415

    capture_state = getattr(window, "capture_state", None)
    if not isinstance(capture_state, CaptureState):
        return False

    if action_id == "capture.capture_mode.close":
        capture_state.enabled = False
        capture_state.drag_anchor = None
        _set_editor_session_flag(window, "set_capture_mode_active", False)
        return True

    if action_id == "capture.capture_mode.toggle_persist_armed":
        window.capture_persist_armed = not bool(getattr(window, "capture_persist_armed", False))
        return True

    if action_id == "capture.capture_mode.toggle_stamp_brush":
        mode = str(getattr(capture_state, "mode", "stamp")).strip().lower()
        capture_state.mode = "brush" if mode != "brush" else "stamp"
        return True

    if action_id == "capture.capture_mode.toggle_entities":
        capture_state.include_entities = not bool(getattr(capture_state, "include_entities", True))
        return True

    if action_id in ("capture.capture_mode.capture", "capture.capture_mode.validate"):
        return _handle_capture_mode_execute(window, capture_state, validate_only=(action_id == "capture.capture_mode.validate"))

    if action_id == "capture.capture_mode.toggle":
        return _handle_capture_mode_toggle(window)

    return False


def _handle_capture_mode_execute(window: Any, capture_state: Any, *, validate_only: bool) -> bool:
    from engine.capture_mode import build_capture_payload  # noqa: PLC0415
    from engine.tooling_runtime.clipboard import try_copy_to_clipboard  # noqa: PLC0415
    from engine.tooling_runtime.capture_persist import persist_capture_payload, validate_brush_payload, validate_stamp_payload  # noqa: PLC0415

    sc = getattr(window, "scene_controller", None)
    scene_payload = getattr(sc, "_loaded_scene_data", None) if sc is not None else None
    if not isinstance(scene_payload, dict):
        print("[Mesh][Capture] ERROR: no loaded scene payload")
        return True

    rect = getattr(capture_state, "rect", None)
    if rect is None:
        print("[Mesh][Capture] ERROR: no selection rect (drag to select)")
        return True

    instance = getattr(sc, "tilemap_instance", None) if sc is not None else None
    if instance is None:
        print("[Mesh][Capture] ERROR: no tilemap instance")
        return True
    map_w, map_h = getattr(instance, "map_size", (0, 0))
    tile_w, tile_h = getattr(instance, "tile_size", (0, 0))

    mode = str(getattr(capture_state, "mode", "stamp")).strip().lower()
    header, out = build_capture_payload(
        scene_payload,
        mode=("brush" if mode == "brush" else "stamp"),
        rect=rect,
        map_width=int(map_w),
        map_height=int(map_h),
        tile_width=int(tile_w) if isinstance(tile_w, int) else None,
        tile_height=int(tile_h) if isinstance(tile_h, int) else None,
        include_entities=bool(getattr(capture_state, "include_entities", True)),
        layer_id=str(getattr(capture_state, "layer_id", "") or "").strip(),
        brush_filter_mode=str(getattr(capture_state, "brush_filter_mode", "nonzero")),  # type: ignore[arg-type]
        brush_filter_value=int(getattr(capture_state, "brush_filter_value", 0)),
    )

    if validate_only:
        if mode == "brush":
            errors = validate_brush_payload(out)
        else:
            errors = validate_stamp_payload(out, rel_path="capture")
        if errors:
            print(f"CAPTURE_VALIDATE fail errors={len(errors)}")
        else:
            print("CAPTURE_VALIDATE ok errors=0")
        return True

    import json  # noqa: PLC0415

    text = json.dumps(out, indent=2, sort_keys=True)
    print(header)
    print(text)
    try_copy_to_clipboard(text)

    if bool(getattr(window, "capture_persist_armed", False)):
        capture_persist_result = persist_capture_payload("brush" if mode == "brush" else "stamp", out)
        if capture_persist_result.ok:
            status = f"CAPTURE_PERSIST ok path={capture_persist_result.path} wrote={'Y' if capture_persist_result.wrote else 'N'}"
        else:
            reason = ",".join(capture_persist_result.errors) if capture_persist_result.errors else "error"
            status = f"CAPTURE_PERSIST fail reason={reason} path={capture_persist_result.path}"
        window.capture_persist_status = status
        print(status)
        if capture_persist_result.ok and capture_persist_result.rel_path:
            try:
                from engine.palette_mode import get_state  # noqa: PLC0415
                get_state().hot_add_item(rel_path=str(capture_persist_result.rel_path))
            except Exception:  # noqa: BLE001
                pass
    return True


def _handle_capture_mode_toggle(window: Any) -> bool:
    from engine.capture_mode import CaptureState, iter_layer_ids_sorted_by_z_id  # noqa: PLC0415

    state = getattr(window, "capture_state", None)
    if not isinstance(state, CaptureState):
        state = CaptureState()
        window.capture_state = state
    state.enabled = not bool(getattr(state, "enabled", False))
    state.drag_anchor = None
    state.rect = None

    if state.enabled and not str(getattr(state, "layer_id", "") or "").strip():
        sc = getattr(window, "scene_controller", None)
        scene_payload = getattr(sc, "_loaded_scene_data", None) if sc is not None else None
        if isinstance(scene_payload, dict):
            ids = iter_layer_ids_sorted_by_z_id(scene_payload)
            state.layer_id = ids[0] if ids else ""
    _set_editor_session_flag(window, "set_capture_mode_active", bool(getattr(state, "enabled", False)))
    return True


__all__ = ["dispatch_palette_action"]
