from __future__ import annotations

from typing import Any

import engine.optional_arcade as optional_arcade

from engine.input_runtime.capture_runtime_focus_model import CaptureFocusSnapshot


def is_interact_key(controller: Any, key: int) -> bool:
    if key == optional_arcade.arcade.key.E:
        return True
    try:
        binder = getattr(controller.manager, "is_key_bound_to_action", None)
        return bool(callable(binder) and binder("interact", key))
    except Exception:  # noqa: BLE001
        return False


def dispatch_global_action(
    controller: Any,
    snapshot: CaptureFocusSnapshot,
    action_id: str,
    *,
    key: int | None = None,
    modifiers: int | None = None,
) -> bool:
    window = controller.window
    if action_id == "capture.interact.primary":
        return _handle_interact_action(controller, snapshot, key=key, modifiers=modifiers)
    if action_id == "capture.perf.toggle":
        return _handle_perf_toggle(window)
    if action_id == "capture.debug.toggle":
        return _handle_debug_toggle(window, controller)
    if action_id == "capture.debug.undo":
        return _handle_debug_undo(window)
    if action_id == "capture.debug.redo":
        return _handle_debug_redo(window)
    if action_id == "capture.palette.toggle":
        return _handle_palette_toggle(window)
    if action_id == "capture.scene.reload":
        return _handle_scene_reload(window)
    if action_id == "capture.scene.persist_toggle":
        return _handle_scene_persist_toggle(window)
    if action_id == "capture.scene.persist":
        return _handle_scene_persist(window)
    if action_id == "capture.scene.save_as":
        return _handle_scene_save_as(window)
    if action_id == "capture.editor.toggle":
        return _handle_editor_toggle(window)
    if action_id == "capture.savegame.save":
        return _handle_savegame_save(window)
    if action_id == "capture.savegame.load_or_play":
        return _handle_savegame_load_or_play(window)
    if action_id == "capture.debug.ai_toggle_or_stop":
        return _handle_ai_toggle_or_stop(window, controller)
    if action_id == "capture.overlay.encounter_debug.toggle":
        return _handle_encounter_debug_toggle(window)
    if action_id == "capture.overlay.scene_inspector.toggle":
        return _handle_scene_inspector_toggle(window)
    if action_id == "capture.debug.copy_coords_or_pause":
        return _handle_copy_coords_or_pause(window)
    if action_id == "capture.debug.copy_hover_coords":
        return _handle_copy_hover_coords(window)
    if action_id == "capture.debug.toggle_selection_lock":
        return _handle_toggle_selection_lock(window)
    if action_id == "capture.settings.toggle":
        return _handle_settings_toggle(window)
    return False


def _ui_blocks_input(window: Any) -> bool:
    ui_ctrl = getattr(window, "ui_controller", None)
    return bool(ui_ctrl and getattr(ui_ctrl, "input_blocked", False))


def _player_input_blocked(window: Any) -> bool:
    ui_ctrl = getattr(window, "ui_controller", None)
    if ui_ctrl and getattr(ui_ctrl, "input_blocked", False):
        return True
    dialogue = getattr(window, "dialogue_controller", None)
    if dialogue and getattr(dialogue, "active", False):
        return True
    return False


def _handle_interact_action(
    controller: Any,
    snapshot: CaptureFocusSnapshot,
    *,
    key: int | None = None,
    modifiers: int | None = None,
) -> bool:
    """Handle interact key (E) - complex due to InputManager integration."""
    window = controller.window
    key_code = int(key) if key is not None else optional_arcade.arcade.key.E
    _mods = int(modifiers) if modifiers is not None else 0

    # Only handle E key or keys bound to interact
    if not is_interact_key(controller, key_code):
        return False

    # Skip if debug mode + Ctrl+E (rotate transform)
    if snapshot.show_debug and snapshot.ctrl and key_code == optional_arcade.arcade.key.E:
        return False

    # Don't handle in editor mode
    if snapshot.editor_active:
        return False

    # Block gameplay interaction when any authoring mode is active (consume key but don't interact)
    if snapshot.is_capture_mode_enabled or snapshot.is_tile_paint_enabled or snapshot.is_entity_paint_enabled or snapshot.is_palette_mode_enabled:
        return True

    # If UI is blocking, fall through to let InputManager record the key
    if _player_input_blocked(window) or _ui_blocks_input(window):
        return False

    # Perform interaction
    from engine.interaction import DEFAULT_INTERACT_MAX_DIST, perform_interaction  # noqa: PLC0415

    if perform_interaction(window, max_dist=DEFAULT_INTERACT_MAX_DIST):
        setattr(window, "_mesh_interact_consumed", True)
        manager = getattr(controller, "manager", None)
        press = getattr(manager, "press", None) if manager is not None else None
        if callable(press):
            press(key_code)
        keys = getattr(controller, "_keys", None)
        if isinstance(keys, set):
            keys.add(key_code)
        return True
    return False


def _handle_perf_toggle(window: Any) -> bool:
    perf = getattr(window, "perf_overlay", None)
    if perf:
        perf.toggle()
    return True


def _handle_debug_toggle(window: Any, controller: Any) -> bool:
    window.show_debug = not window.show_debug
    controller._log_debug(f"[Mesh][Debug] show_debug = {window.show_debug}")
    return True


def _handle_debug_undo(window: Any) -> bool:
    undoer = getattr(window, "undo", None)
    if callable(undoer):
        undoer()
    return True


def _handle_debug_redo(window: Any) -> bool:
    redoer = getattr(window, "redo", None)
    if callable(redoer):
        redoer()
    return True


def _handle_palette_toggle(window: Any) -> bool:
    from engine.palette_mode import toggle_palette  # noqa: PLC0415
    toggle_palette()
    return True


def _handle_scene_reload(window: Any) -> bool:
    reloader = getattr(window, "reload_scene_from_disk", None)
    ok = bool(reloader()) if callable(reloader) else False
    print(f"SCENE_RELOAD {'ok' if ok else 'fail'}")
    return True


def _handle_scene_persist_toggle(window: Any) -> bool:
    window.scene_persist_armed = not bool(getattr(window, "scene_persist_armed", False))
    print(f"SCENE_PERSIST_ARMED {'on' if window.scene_persist_armed else 'off'}")
    return True


def _handle_scene_persist(window: Any) -> bool:
    if not bool(getattr(window, "scene_persist_armed", False)):
        print("SCENE_PERSIST (not armed)")
        return True
    persister = getattr(window, "persist_scene_to_disk", None)
    scene_persist_result = persister() if callable(persister) else None
    ok = bool(getattr(scene_persist_result, "ok", False))
    persist_path = str(getattr(scene_persist_result, "path", "") or "").strip()
    print(f"SCENE_PERSIST {'ok' if ok else 'fail'} path={persist_path or '-'}")
    return True


def _handle_scene_save_as(window: Any) -> bool:
    from engine.entity_select_mode import other_authoring_modes_active  # noqa: PLC0415

    if other_authoring_modes_active(window):
        return True
    if not bool(getattr(window, "scene_persist_armed", False)):
        print("SCENE_SAVE_AS (not armed)")
        return True
    saver = getattr(window, "save_scene_as", None)
    save_as_result = saver("") if callable(saver) else None
    ok = bool(getattr(save_as_result, "ok", False))
    out_path = str(getattr(save_as_result, "path", "") or "").strip()
    if ok and out_path:
        print(f"TIP: python -m mesh_cli world add-scene worlds/main_world.json --key <key> --path {out_path}")
    return True


def _handle_editor_toggle(window: Any) -> bool:
    window.editor_controller.toggle()
    return True


def _handle_savegame_save(window: Any) -> bool:
    from engine import savegame  # noqa: PLC0415

    save = savegame.capture_savegame_from_window(window)
    if save is None:
        logger = getattr(window, "console_log", None)
        if callable(logger):
            logger("[SaveGame] No active scene/player to save.")
        return True
    try:
        save_path = savegame.resolve_savegame_path()
        savegame.save_savegame(save_path, save)
        logger = getattr(window, "console_log", None)
        if callable(logger):
            logger(f"[SaveGame] Saved to {save_path}")
    except Exception as exc:  # noqa: BLE001
        logger = getattr(window, "console_log", None)
        if callable(logger):
            logger(f"[SaveGame] Save failed: {exc}")
    return True


def _handle_savegame_load_or_play(window: Any) -> bool:
    editor = getattr(window, "editor_controller", None)
    session = getattr(editor, "play_session", None) if editor is not None else None
    if session is not None and getattr(session, "is_playing", False):
        return True
    if editor is not None and getattr(editor, "active", False):
        starter = getattr(editor, "play_from_here", None)
        if callable(starter):
            starter()
            return True

    from engine import savegame  # noqa: PLC0415

    try:
        save_path = savegame.resolve_savegame_path()
        save = savegame.load_savegame(save_path)
        if save is None:
            logger = getattr(window, "console_log", None)
            if callable(logger):
                logger(f"[SaveGame] No save file at {save_path}")
            return True
        savegame.apply_savegame_to_window(window, save)
        logger = getattr(window, "console_log", None)
        if callable(logger):
            logger(f"[SaveGame] Loaded from {save_path}")
    except Exception as exc:  # noqa: BLE001
        logger = getattr(window, "console_log", None)
        if callable(logger):
            logger(f"[SaveGame] Load failed: {exc}")
    return True


def _handle_ai_toggle_or_stop(window: Any, controller: Any) -> bool:
    editor = getattr(window, "editor_controller", None)
    session = getattr(editor, "play_session", None) if editor is not None else None
    if session is not None and getattr(session, "is_playing", False):
        stopper = getattr(editor, "stop_playing", None)
        if callable(stopper):
            stopper()
        return True
    window.ai_debug_overlay_enabled = not window.ai_debug_overlay_enabled
    controller._log_debug(f"[Mesh][Debug] AI Overlay = {window.ai_debug_overlay_enabled}")
    return True


def _handle_encounter_debug_toggle(window: Any) -> bool:
    overlay = getattr(window, "encounter_debug_overlay", None)
    toggle = getattr(overlay, "toggle", None)
    if callable(toggle):
        toggle()
    return True


def _handle_scene_inspector_toggle(window: Any) -> bool:
    overlay = getattr(window, "scene_inspector_overlay", None)
    toggle = getattr(overlay, "toggle", None)
    if callable(toggle):
        toggle()
    return True


def _handle_copy_coords_or_pause(window: Any) -> bool:
    overlay = getattr(window, "scene_inspector_overlay", None)
    debug_active = bool(getattr(window, "show_debug", False)) or bool(getattr(overlay, "visible", False))

    if debug_active:
        from engine.tooling_runtime.authoring_snippets import (  # noqa: PLC0415
            build_player_pos_snippet,
            get_effective_hover_payload,
            get_scene_inspector_payload,
        )
        from engine.tooling_runtime.clipboard import try_copy_to_clipboard  # noqa: PLC0415

        inspector_payload = get_scene_inspector_payload(window)
        effective_payload = get_effective_hover_payload(window, inspector_payload)
        snippet = build_player_pos_snippet(effective_payload)
        print(snippet)
        try_copy_to_clipboard(snippet)
        return True

    new_state = window._toggle_paused_state()
    window.console_log(f"Paused = {new_state}")
    return True


def _handle_copy_hover_coords(window: Any) -> bool:
    from engine.tooling_runtime.authoring_snippets import (  # noqa: PLC0415
        build_hover_pos_snippet,
        get_effective_hover_payload,
        get_scene_inspector_payload,
    )
    from engine.tooling_runtime.clipboard import try_copy_to_clipboard  # noqa: PLC0415

    inspector_payload = get_scene_inspector_payload(window)
    effective_payload = get_effective_hover_payload(window, inspector_payload)
    snippet = build_hover_pos_snippet(effective_payload)
    print(snippet)
    try_copy_to_clipboard(snippet)
    return True


def _handle_toggle_selection_lock(window: Any) -> bool:
    from engine.tooling_runtime.authoring_snippets import (  # noqa: PLC0415
        get_scene_inspector_payload,
        toggle_locked_selection_from_hover,
    )

    inspector_payload = get_scene_inspector_payload(window)
    selected = toggle_locked_selection_from_hover(window, inspector_payload)
    logger = getattr(window, "console_log", None)
    if callable(logger):
        if selected is None:
            logger("[Authoring] Selection cleared")
        else:
            logger(f"[Authoring] Selection locked: {selected}")
    return True


def _handle_settings_toggle(window: Any) -> bool:
    overlay = getattr(window, "settings_overlay", None)
    toggle = getattr(overlay, "toggle", None) if overlay is not None else None
    if callable(toggle):
        toggle()
        return True
    return False


__all__ = ["dispatch_global_action", "is_interact_key"]
