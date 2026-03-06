from __future__ import annotations

import json
from typing import Any

from ._shared import _get_authored_payload, _get_selection_ids_and_primary, _log_swallow, _resolve_macro_anchor_pos

def action_toggle_tile_paint(w: Any, _arg: str | None) -> None:
    """Toggle tile paint mode."""
    state = getattr(w, "tile_paint_state", None)
    if state is None:
        return
    state.enabled = not bool(getattr(state, "enabled", False))
    if bool(getattr(state, "enabled", False)) and not str(getattr(state, "layer_id", "") or "").strip():
        sc = getattr(w, "scene_controller", None)
        payload = getattr(sc, "_loaded_scene_data", None) if sc is not None else None
        tilemap_value = payload.get("tilemap") if isinstance(payload, dict) else None
        tilemap = tilemap_value if isinstance(tilemap_value, dict) else {}
        from engine.tile_paint_mode import cycle_layer_id  # noqa: PLC0415
        tile_layers = tilemap.get("tile_layers")
        tile_layers_list = tile_layers if isinstance(tile_layers, list) else []
        state.layer_id = cycle_layer_id(tile_layers=tile_layers_list, current="", direction=1)


def action_toggle_entity_paint(w: Any, _arg: str | None) -> None:
    """Toggle entity paint mode."""
    from engine.entity_paint_mode import EntityPaintState, load_prefab_infos  # noqa: PLC0415
    state = getattr(w, "entity_paint_state", None)
    if not isinstance(state, EntityPaintState):
        return
    state.enabled = not bool(getattr(state, "enabled", False))
    if state.enabled and not getattr(state, "prefabs", ()):
        state.prefabs = load_prefab_infos()
        state.selected_index = 0
    if not state.enabled:
        state.persist_armed = False


def action_toggle_palette_mode(_w: Any, _arg: str | None) -> None:
    """Toggle palette mode."""
    from engine.palette_mode import toggle_palette  # noqa: PLC0415
    toggle_palette()


def action_toggle_capture(w: Any, _arg: str | None) -> None:
    """Toggle capture mode."""
    from engine.capture_mode import CaptureState, iter_layer_ids_sorted_by_z_id  # noqa: PLC0415
    state = getattr(w, "capture_state", None)
    if not isinstance(state, CaptureState):
        state = CaptureState()
        w.capture_state = state
    state.enabled = not bool(getattr(state, "enabled", False))
    state.drag_anchor = None
    state.rect = None
    if state.enabled and not str(getattr(state, "layer_id", "") or "").strip():
        sc = getattr(w, "scene_controller", None)
        payload = getattr(sc, "_loaded_scene_data", None) if sc is not None else None
        if isinstance(payload, dict):
            ids = iter_layer_ids_sorted_by_z_id(payload)
            state.layer_id = ids[0] if ids else ""


def action_toggle_ghost_originals(w: Any, _arg: str | None) -> None:
    """Toggle ghost originals display."""
    editor = getattr(w, "editor_controller", None)
    if editor is None:
        return
    toggler = getattr(editor, "toggle_ghost_originals", None)
    if callable(toggler):
        toggler()


def action_palette_clear_recent(w: Any, _arg: str | None) -> None:
    try:
        from engine.command_palette_controller import clear_command_palette_recent_commands  # noqa: PLC0415
    except Exception:
        _log_swallow(
            "CPRA-005",
            "engine.command_palette_registry_actions_impl.action_palette_clear_recent",
            "import_clear_command_palette_recent_commands",
        )
        return
    removed = int(clear_command_palette_recent_commands(w))
    print(f"PALETTE_RECENT_CLEAR count={removed}")


def action_palette_reset_ui_layout(w: Any, _arg: str | None) -> None:
    try:
        from engine.editor.editor_ui_state import (  # noqa: PLC0415
            EditorUiState,
            apply_editor_ui_state,
            reset_editor_ui_state,
        )
    except Exception:
        _log_swallow(
            "CPRA-006",
            "engine.command_palette_registry_actions_impl.action_palette_reset_ui_layout",
            "import_editor_ui_state",
        )
        return
    editor = getattr(w, "editor_controller", None)
    if editor is None:
        print("PALETTE_UI_LAYOUT_RESET ok removed=0")
        return
    removed = bool(reset_editor_ui_state())
    apply_editor_ui_state(editor, EditorUiState())
    print(f"PALETTE_UI_LAYOUT_RESET ok removed={1 if removed else 0}")


def action_macro_objective_zone(w: Any, arg: str | None) -> None:
    """Execute objective zone macro."""
    sc = getattr(w, "scene_controller", None)
    if sc is None:
        print("AUTHOR_MACRO noop reason=no_scene")
        return
    if _get_authored_payload(w) is None:
        print("AUTHOR_MACRO noop reason=no_authored_payload")
        return

    try:
        data = json.loads(str(arg or "") or "{}")
    except Exception:  # noqa: BLE001  # REASON: runtime fallback isolation
        _log_swallow(
            "CPRA-009",
            "engine.command_palette_registry_actions_impl.action_macro_objective_zone",
            "parse_json_args",
        )
        data = {}
    if not isinstance(data, dict):
        data = {}

    anchor = str(data.get("anchor") or "cursor").strip().lower() or "cursor"
    zone_id = str(data.get("zone_id") or "").strip()
    set_flag = str(data.get("set_flag") or "").strip()
    radius_raw = str(data.get("radius") or "").strip()
    toast = str(data.get("toast") or "")
    toast = toast.strip() if isinstance(toast, str) else ""
    toast_val = toast if toast else None
    req_raw = data.get("require_flags")
    forb_raw = data.get("forbid_flags")
    toast_seconds_raw = data.get("toast_seconds")
    require_flags = [str(v).strip() for v in (req_raw or []) if isinstance(req_raw, list) and str(v).strip()] if isinstance(req_raw, list) else None
    forbid_flags = [str(v).strip() for v in (forb_raw or []) if isinstance(forb_raw, list) and str(v).strip()] if isinstance(forb_raw, list) else None
    toast_seconds: float | None
    if toast_seconds_raw is None or toast_seconds_raw == "":
        toast_seconds = None
    else:
        try:
            toast_seconds = float(toast_seconds_raw)
        except Exception:  # noqa: BLE001  # REASON: runtime fallback isolation
            _log_swallow(
                "CPRA-010",
                "engine.command_palette_registry_actions_impl.action_macro_objective_zone",
                "parse_toast_seconds",
            )
            toast_seconds = None
    try:
        radius = float(radius_raw)
    except Exception:  # noqa: BLE001  # REASON: runtime fallback isolation
        _log_swallow(
            "CPRA-011",
            "engine.command_palette_registry_actions_impl.action_macro_objective_zone",
            "parse_radius",
        )
        print("AUTHOR_MACRO noop reason=bad_args")
        return
    if not zone_id or not set_flag:
        print("AUTHOR_MACRO noop reason=bad_args")
        return

    pos, reason = _resolve_macro_anchor_pos(w, anchor)
    if reason:
        print(f"AUTHOR_MACRO noop reason={reason}")
        return
    if pos is None:
        pos = (0.0, 0.0)

    payload_new, created, updated = sc.debug_build_macro_objective_zone_payload(
        center_x=float(pos[0]),
        center_y=float(pos[1]),
        zone_id=zone_id,
        set_flag=set_flag,
        radius=float(radius),
        toast=toast_val,
        require_flags=require_flags,
        forbid_flags=forbid_flags,
        toast_seconds=toast_seconds,
    )
    authored = sc.get_authored_scene_payload()
    if payload_new == authored:
        print("AUTHOR_MACRO noop reason=no_changes")
        return

    pusher = getattr(w, "push_undo_frame", None)
    if callable(pusher):
        pusher("entity_macro_objective_zone")
    sc.debug_apply_authored_scene_payload(payload_new)
    marker = getattr(w, "mark_scene_dirty", None)
    if callable(marker):
        marker("macro_objective_zone")
    last_args = getattr(w, "last_macro_args", None)
    if isinstance(last_args, dict):
        stored: dict[str, Any] = {
            "anchor": anchor,
            "zone_id": zone_id,
            "set_flag": set_flag,
            "radius": float(radius),
            "toast": toast,
        }
        if "toast_seconds" in data:
            stored["toast_seconds"] = float(toast_seconds) if isinstance(toast_seconds, (int, float)) else ""
        if "require_flags" in data:
            stored["require_flags"] = require_flags or []
        if "forbid_flags" in data:
            stored["forbid_flags"] = forbid_flags or []
        last_args["macro.objective_zone"] = stored
    print(f"AUTHOR_MACRO ok action=objective_zone created={int(created)} updated={int(updated)}")


def action_macro_door_transition(w: Any, arg: str | None) -> None:
    """Execute door transition macro."""
    sc = getattr(w, "scene_controller", None)
    if sc is None:
        print("AUTHOR_MACRO noop reason=no_scene")
        return
    if _get_authored_payload(w) is None:
        print("AUTHOR_MACRO noop reason=no_authored_payload")
        return

    try:
        data = json.loads(str(arg or "") or "{}")
    except Exception:  # noqa: BLE001  # REASON: runtime fallback isolation
        _log_swallow(
            "CPRA-012",
            "engine.command_palette_registry_actions_impl.action_macro_door_transition",
            "parse_json_args",
        )
        data = {}
    if not isinstance(data, dict):
        data = {}

    anchor = str(data.get("anchor") or "cursor").strip().lower() or "cursor"
    target_scene = str(data.get("target_scene") or "").strip()
    spawn_id = str(data.get("spawn_id") or "").strip()
    if not target_scene or not spawn_id:
        print("AUTHOR_MACRO noop reason=bad_args")
        return

    _selected_ids, primary_id = _get_selection_ids_and_primary(w)
    pos, reason = _resolve_macro_anchor_pos(w, anchor)
    if reason:
        print(f"AUTHOR_MACRO noop reason={reason}")
        return
    if pos is None:
        pos = (0.0, 0.0)
    payload_new, created, updated = sc.debug_build_macro_door_transition_payload(
        center_x=float(pos[0]),
        center_y=float(pos[1]),
        target_scene=target_scene,
        spawn_id=spawn_id,
        primary_id=primary_id if primary_id else None,
    )
    authored = sc.get_authored_scene_payload()
    if payload_new == authored:
        print("AUTHOR_MACRO noop reason=no_changes")
        return

    pusher = getattr(w, "push_undo_frame", None)
    if callable(pusher):
        pusher("entity_macro_door_transition")
    sc.debug_apply_authored_scene_payload(payload_new)
    marker = getattr(w, "mark_scene_dirty", None)
    if callable(marker):
        marker("macro_door_transition")
    last_args = getattr(w, "last_macro_args", None)
    if isinstance(last_args, dict):
        last_args["macro.door_transition"] = {
            "anchor": anchor,
            "target_scene": target_scene,
            "spawn_id": spawn_id,
        }
    print(f"AUTHOR_MACRO ok action=door_transition created={int(created)} updated={int(updated)}")


def action_macro_dialogue_choice_flag(w: Any, arg: str | None) -> None:
    """Execute dialogue choice flag macro."""
    sc = getattr(w, "scene_controller", None)
    if sc is None:
        print("AUTHOR_MACRO noop reason=no_scene")
        return
    if _get_authored_payload(w) is None:
        print("AUTHOR_MACRO noop reason=no_authored_payload")
        return

    try:
        data = json.loads(str(arg or "") or "{}")
    except Exception:  # noqa: BLE001  # REASON: runtime fallback isolation
        _log_swallow(
            "CPRA-013",
            "engine.command_palette_registry_actions_impl.action_macro_dialogue_choice_flag",
            "parse_json_args",
        )
        data = {}
    if not isinstance(data, dict):
        data = {}

    speaker_id = str(data.get("speaker_id") or "").strip()
    choice_id = str(data.get("choice_id") or "").strip()
    choice_text = str(data.get("choice_text") or "").strip()
    set_flag = str(data.get("set_flag") or "").strip()
    toast = str(data.get("toast") or "")
    toast = toast.strip() if isinstance(toast, str) else ""
    toast_val = toast if toast else None
    if not speaker_id or not choice_id or not choice_text or not set_flag:
        print("AUTHOR_MACRO noop reason=bad_args")
        return

    payload_new, created, updated = sc.debug_build_macro_dialogue_choice_flag_payload(
        speaker_id=speaker_id,
        choice_id=choice_id,
        choice_text=choice_text,
        set_flag=set_flag,
        toast=toast_val,
    )
    authored = sc.get_authored_scene_payload()
    if payload_new == authored:
        print("AUTHOR_MACRO noop reason=no_changes")
        return

    pusher = getattr(w, "push_undo_frame", None)
    if callable(pusher):
        pusher("entity_macro_dialogue_choice_flag")
    sc.debug_apply_authored_scene_payload(payload_new)
    marker = getattr(w, "mark_scene_dirty", None)
    if callable(marker):
        marker("macro_dialogue_choice_flag")
    last_args = getattr(w, "last_macro_args", None)
    if isinstance(last_args, dict):
        last_args["macro.dialogue_choice_flag"] = {
            "speaker_id": speaker_id,
            "choice_id": choice_id,
            "choice_text": choice_text,
            "set_flag": set_flag,
            "toast": toast,
        }
    print(f"AUTHOR_MACRO ok action=dialogue_choice_flag created={int(created)} updated={int(updated)}")
