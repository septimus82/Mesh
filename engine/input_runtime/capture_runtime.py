from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast
import engine.optional_arcade as optional_arcade

from engine.input_runtime.capture_io import _recent_push_int, _recent_push_many, _recent_push_str

if TYPE_CHECKING:
    from engine.input_controller import InputController


def ui_blocks_input(controller: "InputController") -> bool:
    ui_ctrl = getattr(controller.window, "ui_controller", None)
    return bool(ui_ctrl and getattr(ui_ctrl, "input_blocked", False))


def handle_key_press(controller: "InputController", key: int, modifiers: int) -> bool:
    """
    Handle key press events with capture priority.

    Returns True if the event was consumed and should not propagate further.
    """
    window = controller.window
    try:
        setattr(window, "_debug_last_modifiers", int(modifiers))
    except Exception:  # noqa: BLE001
        pass

    # Perf overlay toggle (P)
    if key == optional_arcade.arcade.key.P and not (modifiers & optional_arcade.arcade.key.MOD_CTRL):
        perf = getattr(window, "perf_overlay", None)
        if perf:
            perf.toggle()
        return True

    # Always allow toggling the console, even if debug mode is off.
    if key in (optional_arcade.arcade.key.GRAVE, optional_arcade.arcade.key.INSERT, optional_arcade.arcade.key.F1) and not (modifiers & optional_arcade.arcade.key.MOD_CTRL):
        # If another modal debug UI is open, close it to avoid text-input conflicts.
        if getattr(window, "command_palette_enabled", False) is True:
            window.command_palette_enabled = False
            window.command_palette_prompt_active = False
        window.console_controller.toggle()
        return True

    # Debug-only command palette uses Ctrl+F1 so it doesn't steal F1 from the console.
    if bool(getattr(window, "show_debug", False)) and key == optional_arcade.arcade.key.F1 and (modifiers & optional_arcade.arcade.key.MOD_CTRL):
        window.command_palette_enabled = not bool(getattr(window, "command_palette_enabled", False))
        if bool(getattr(window, "command_palette_enabled", False)):
            window.command_palette_query = ""
            window.command_palette_index = 0
            window.command_palette_prompt_active = False
            window.command_palette_prompt_text = ""
            window.command_palette_prompt_kind = "text"
            window.command_palette_prompt_query = ""
            window.command_palette_prompt_index = 0
            window.command_palette_prompt_steps = ()
            window.command_palette_prompt_step_index = 0
            window.command_palette_prompt_values = {}
        return True

    if bool(getattr(window, "show_debug", False)) and getattr(window, "command_palette_enabled", False) is True:
        if key == optional_arcade.arcade.key.ESCAPE:
            if bool(getattr(window, "command_palette_prompt_active", False)):
                window.command_palette_prompt_active = False
                window.command_palette_prompt_text = ""
                window.command_palette_prompt_query = ""
                return True
            window.command_palette_enabled = False
            return True
        
        if key == optional_arcade.arcade.key.UP:
            if bool(getattr(window, "command_palette_prompt_active", False)):
                prompt_kind = str(getattr(window, "command_palette_prompt_kind", "text") or "text").strip().lower()
                if prompt_kind == "pick":
                    idx = int(getattr(window, "command_palette_prompt_index", 0) or 0)
                    window.command_palette_prompt_index = max(0, idx - 1)
                return True
            idx = int(getattr(window, "command_palette_index", 0) or 0)
            window.command_palette_index = max(0, idx - 1)
            return True
        
        if key == optional_arcade.arcade.key.DOWN:
            if bool(getattr(window, "command_palette_prompt_active", False)):
                prompt_kind = str(getattr(window, "command_palette_prompt_kind", "text") or "text").strip().lower()
                if prompt_kind == "pick":
                    idx = int(getattr(window, "command_palette_prompt_index", 0) or 0)
                    window.command_palette_prompt_index = idx + 1
                return True
            idx = int(getattr(window, "command_palette_index", 0) or 0)
            window.command_palette_index = idx + 1
            return True

        if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
            import json as _json  # noqa: PLC0415
            from engine.command_palette import build_default_commands, filter_commands, filter_options  # noqa: PLC0415

            commands = build_default_commands(window)
            by_id = {c.id: c for c in commands}

            # Prompt commit.
            if bool(getattr(window, "command_palette_prompt_active", False)):
                cmd_id = str(getattr(window, "command_palette_prompt_command_id", "") or "")
                cmd = by_id.get(cmd_id)
                if cmd is None:
                    return True

                steps = getattr(window, "command_palette_prompt_steps", ())
                step_idx = int(getattr(window, "command_palette_prompt_step_index", 0) or 0)
                values = getattr(window, "command_palette_prompt_values", {})
                if not isinstance(values, dict):
                    values = {}

                current_prompt = None
                if isinstance(steps, tuple) and steps and 0 <= step_idx < len(steps):
                    current_prompt = steps[step_idx]
                elif getattr(cmd, "prompt", None) is not None:
                    current_prompt = cmd.prompt

                if current_prompt is None:
                    window.command_palette_prompt_active = False
                    return True

                prompt_kind = str(getattr(current_prompt, "kind", "text") or "text").strip().lower()
                if prompt_kind == "pick":
                    provider = getattr(current_prompt, "options_provider", None)
                    options = provider(window) if callable(provider) else []
                    filtered = filter_options(options, str(getattr(window, "command_palette_prompt_query", "") or ""))
                    if not filtered:
                        return True
                    pidx = int(getattr(window, "command_palette_prompt_index", 0) or 0)
                    pidx = max(0, min(pidx, len(filtered) - 1))
                    val: str | None = str(filtered[pidx][0])
                else:
                    val = str(getattr(window, "command_palette_prompt_text", "") or "")

                if isinstance(steps, tuple) and steps:
                    key_name = str(getattr(current_prompt, "field", None) or f"arg{step_idx}")
                    values[key_name] = val
                    window.command_palette_prompt_values = values
                    next_idx = step_idx + 1
                    if next_idx < len(steps):
                        next_step = steps[next_idx]
                        window.command_palette_prompt_step_index = next_idx
                        window.command_palette_prompt_title = f"{cmd.title} ({next_idx + 1}/{len(steps)})"
                        window.command_palette_prompt_placeholder = str(getattr(next_step, "placeholder", "") or "")
                        window.command_palette_prompt_kind = str(getattr(next_step, "kind", "text") or "text")
                        window.command_palette_prompt_index = 0
                        try:
                            default_value = str(next_step.default_value_fn(window) or "")
                        except Exception:  # noqa: BLE001
                            default_value = ""
                        if str(window.command_palette_prompt_kind).strip().lower() == "pick":
                            window.command_palette_prompt_query = default_value
                            window.command_palette_prompt_text = ""
                        else:
                            window.command_palette_prompt_text = default_value
                            window.command_palette_prompt_query = ""
                        return True

                    try:
                        cmd.action(window, _json.dumps(values, sort_keys=True))
                    except Exception:  # noqa: BLE001
                        pass
                else:
                    try:
                        cmd.action(window, val)
                    except Exception:  # noqa: BLE001
                        pass

                print(f"PALETTE_RUN ok id={cmd.id} title={cmd.title}")
                window.command_palette_prompt_active = False
                window.command_palette_enabled = False
                window.command_palette_prompt_text = ""
                window.command_palette_prompt_query = ""
                return True

            # Execute selected command.
            query = str(getattr(window, "command_palette_query", "") or "")
            filtered_cmds = filter_commands(commands, query)
            if not filtered_cmds:
                return True
            idx = int(getattr(window, "command_palette_index", 0) or 0)
            idx = max(0, min(idx, len(filtered_cmds) - 1))
            cmd = filtered_cmds[idx]

            if (modifiers & optional_arcade.arcade.key.MOD_CTRL) and str(getattr(cmd, "macro_id", "") or "").strip():
                macro_id = str(getattr(cmd, "macro_id", "") or "").strip()
                last_args = getattr(window, "last_macro_args", None)
                last_args = last_args if isinstance(last_args, dict) else {}
                args = last_args.get(macro_id)
                if not isinstance(args, dict):
                    print("AUTHOR_MACRO noop reason=no_last_args")
                    return True
                cmd.action(window, _json.dumps(args, sort_keys=True))
                return True

            enabled, reason = True, ""
            try:
                enabled, reason = cmd.is_enabled(window)
            except Exception:  # noqa: BLE001
                enabled, reason = True, ""
            if not enabled:
                reason_text = str(reason or "disabled").strip()
                print(f"PALETTE_RUN noop id={cmd.id} reason={reason_text}")
                return True

            steps = getattr(cmd, "prompts", None)
            if isinstance(steps, tuple) and steps:
                first = steps[0]
                window.command_palette_prompt_active = True
                window.command_palette_prompt_command_id = cmd.id
                window.command_palette_prompt_steps = steps
                window.command_palette_prompt_step_index = 0
                window.command_palette_prompt_values = {}
                window.command_palette_prompt_title = f"{cmd.title} (1/{len(steps)})"
                window.command_palette_prompt_placeholder = str(getattr(first, "placeholder", "") or "")
                window.command_palette_prompt_kind = str(getattr(first, "kind", "text") or "text")
                window.command_palette_prompt_index = 0
                try:
                    default_value = str(first.default_value_fn(window) or "")
                except Exception:  # noqa: BLE001
                    default_value = ""
                if str(window.command_palette_prompt_kind).strip().lower() == "pick":
                    window.command_palette_prompt_query = default_value
                    window.command_palette_prompt_text = ""
                else:
                    window.command_palette_prompt_text = default_value
                    window.command_palette_prompt_query = ""
                return True

            prompt = getattr(cmd, "prompt", None)
            if prompt is not None:
                window.command_palette_prompt_active = True
                window.command_palette_prompt_command_id = cmd.id
                window.command_palette_prompt_title = cmd.title
                window.command_palette_prompt_placeholder = str(getattr(prompt, "placeholder", "") or "")
                window.command_palette_prompt_kind = str(getattr(prompt, "kind", "text") or "text")
                window.command_palette_prompt_index = 0
                window.command_palette_prompt_steps = ()
                window.command_palette_prompt_step_index = 0
                window.command_palette_prompt_values = {}
                try:
                    default_value = str(prompt.default_value_fn(window) or "")
                except Exception:  # noqa: BLE001
                    default_value = ""
                if str(window.command_palette_prompt_kind).strip().lower() == "pick":
                    window.command_palette_prompt_query = default_value
                    window.command_palette_prompt_text = ""
                else:
                    window.command_palette_prompt_text = default_value
                    window.command_palette_prompt_query = ""
                return True

            try:
                cmd.action(window, None)
            except Exception:  # noqa: BLE001
                pass
            print(f"PALETTE_RUN ok id={cmd.id} title={cmd.title}")
            window.command_palette_enabled = False
            return True

        # Block everything else (text input is handled by handle_text).
        return True

    if window.console_controller.active:
        if window.console_controller.process_key(key, modifiers):
            return True

    # Debug-only undo/redo for authored scene mutations.
    if (
        bool(getattr(window, "show_debug", False))
        and not bool(getattr(getattr(window, "editor_controller", None), "active", False))
        and (modifiers & optional_arcade.arcade.key.MOD_CTRL)
        and not ui_blocks_input(controller)
    ):
        if key == optional_arcade.arcade.key.Z:
            undoer = getattr(window, "undo", None)
            if callable(undoer):
                undoer()
                return True
        if key == optional_arcade.arcade.key.Y:
            redoer = getattr(window, "redo", None)
            if callable(redoer):
                redoer()
                return True

    if key == optional_arcade.arcade.key.F3:
        if not getattr(window, "show_debug", False):
            return False
        from engine.palette_mode import toggle_palette
        toggle_palette()
        return True

    from engine.palette_mode import get_state, toggle_mode, move_selection, toggle_preview, apply_at
    palette_state = get_state()
    if palette_state.enabled and getattr(window, "show_debug", False):
        if key == optional_arcade.arcade.key.TAB:
            toggle_mode()
            return True
        elif key == optional_arcade.arcade.key.UP:
            move_selection(-1)
            return True
        elif key == optional_arcade.arcade.key.DOWN:
            move_selection(1)
            return True
        elif key == optional_arcade.arcade.key.P:
            toggle_preview()
            return True
        elif key == optional_arcade.arcade.key.ENTER:
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

                if modifiers & optional_arcade.arcade.key.MOD_CTRL:
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
        
        # Block specific gameplay keys
        if key in (optional_arcade.arcade.key.E, optional_arcade.arcade.key.SPACE):
            return True

    # Forward to UIController for menu handling
    if window.ui_controller.on_key_press(key, modifiers):
        return True

    from engine.capture_mode import CaptureState  # noqa: PLC0415

    capture_state = getattr(window, "capture_state", None)
    if isinstance(capture_state, CaptureState) and bool(getattr(window, "show_debug", False)) and bool(getattr(capture_state, "enabled", False)):
        if key == optional_arcade.arcade.key.F4:
            window.capture_persist_armed = not bool(getattr(window, "capture_persist_armed", False))
            return True
        if key in (optional_arcade.arcade.key.F2, optional_arcade.arcade.key.ESCAPE):
            capture_state.enabled = False
            capture_state.drag_anchor = None
            return True
        if key == optional_arcade.arcade.key.TAB:
            mode = str(getattr(capture_state, "mode", "stamp")).strip().lower()
            capture_state.mode = "brush" if mode != "brush" else "stamp"
            return True
        if key in (optional_arcade.arcade.key.LSHIFT, optional_arcade.arcade.key.RSHIFT):
            capture_state.include_entities = not bool(getattr(capture_state, "include_entities", True))
            return True
        if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
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

            validate_only = bool(modifiers & (optional_arcade.arcade.key.MOD_SHIFT | optional_arcade.arcade.key.MOD_CTRL))
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

        return True

    if key == optional_arcade.arcade.key.F2 and bool(getattr(window, "show_debug", False)):
        from engine.capture_mode import iter_layer_ids_sorted_by_z_id  # noqa: PLC0415

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
        return True

    if key == optional_arcade.arcade.key.HOME and bool(getattr(window, "show_debug", False)):
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
        return True

    from engine.entity_paint_mode import EntityPaintState  # noqa: PLC0415

    entity_state = getattr(window, "entity_paint_state", None)
    if isinstance(entity_state, EntityPaintState) and bool(getattr(window, "show_debug", False)) and bool(getattr(entity_state, "enabled", False)):
        if key == optional_arcade.arcade.key.F4:
            entity_state.persist_armed = not bool(getattr(entity_state, "persist_armed", False))
            return True

        if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
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

            validate_only = bool(modifiers & (optional_arcade.arcade.key.MOD_SHIFT | optional_arcade.arcade.key.MOD_CTRL))
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

    # Debug-only scene reload/persist hotkeys (avoid conflicts with savegame F5/F6 etc).
    if bool(getattr(window, "show_debug", False)) and not ui_blocks_input(controller):
        if key == optional_arcade.arcade.key.F5 and bool(getattr(window.editor_controller, "active", False)):
            reloader = getattr(window, "reload_scene_from_disk", None)
            ok = bool(reloader()) if callable(reloader) else False
            print(f"SCENE_RELOAD {'ok' if ok else 'fail'}")
            return True
        if key == optional_arcade.arcade.key.R and bool(modifiers & optional_arcade.arcade.key.MOD_CTRL):
            reloader = getattr(window, "reload_scene_from_disk", None)
            ok = bool(reloader()) if callable(reloader) else False
            print(f"SCENE_RELOAD {'ok' if ok else 'fail'}")
            return True

        if key == optional_arcade.arcade.key.A and bool(modifiers & optional_arcade.arcade.key.MOD_CTRL) and bool(modifiers & optional_arcade.arcade.key.MOD_SHIFT):
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
                print(
                    f"TIP: python -m mesh_cli world add-scene worlds/main_world.json --key <key> --path {out_path}"
                )
            return True

        if key == optional_arcade.arcade.key.S and bool(modifiers & optional_arcade.arcade.key.MOD_CTRL):
            if modifiers & optional_arcade.arcade.key.MOD_SHIFT:
                window.scene_persist_armed = not bool(getattr(window, "scene_persist_armed", False))
                print(f"SCENE_PERSIST_ARMED {'on' if window.scene_persist_armed else 'off'}")
                return True
            if not bool(getattr(window, "scene_persist_armed", False)):
                print("SCENE_PERSIST (not armed)")
                return True
            persister = getattr(window, "persist_scene_to_disk", None)
            scene_persist_result = persister() if callable(persister) else None
            ok = bool(getattr(scene_persist_result, "ok", False))
            persist_path = str(getattr(scene_persist_result, "path", "") or "").strip()
            print(f"SCENE_PERSIST {'ok' if ok else 'fail'} path={persist_path or '-'}")
            return True

    if key == optional_arcade.arcade.key.ESCAPE:
        overlay = getattr(window, "settings_overlay", None)
        toggle = getattr(overlay, "toggle", None) if overlay is not None else None
        if callable(toggle):
            toggle()
            return True

    interact_bound = False
    try:
        binder = getattr(controller.manager, "is_key_bound_to_action", None)
        interact_bound = bool(callable(binder) and binder("interact", key))
    except Exception:  # noqa: BLE001
        interact_bound = False

    if (key == optional_arcade.arcade.key.E or interact_bound) and not (
        bool(getattr(window, "show_debug", False)) and (modifiers & optional_arcade.arcade.key.MOD_CTRL) and key == optional_arcade.arcade.key.E
    ):
        if getattr(window.editor_controller, "active", False):
            return False

        # Avoid triggering new interactions while UI/dialogue is blocking input.
        #
        # IMPORTANT: Do not early-return here. Dialogue/choice handling is driven by
        # behaviours that read InputManager action state (e.g. "interact"). Those
        # behaviours must still see the key press even when UI is blocking input.
        if player_input_blocked(controller) or ui_blocks_input(controller):
            # Fall through so the key press is recorded by InputManager below.
            pass
        else:
            from engine.interaction import DEFAULT_INTERACT_MAX_DIST, perform_interaction  # noqa: PLC0415

            if perform_interaction(window, max_dist=DEFAULT_INTERACT_MAX_DIST):
                setattr(window, "_mesh_interact_consumed", True)
                manager = getattr(controller, "manager", None)
                press = getattr(manager, "press", None) if manager is not None else None
                if callable(press):
                    press(key)
                keys = getattr(controller, "_keys", None)
                if isinstance(keys, set):
                    keys.add(key)
                return True
            return False

    if key == optional_arcade.arcade.key.F8:
        overlay = getattr(window, "encounter_debug_overlay", None)
        toggle = getattr(overlay, "toggle", None)
        if callable(toggle):
            toggle()
        return True

    if key == optional_arcade.arcade.key.F10:
        overlay = getattr(window, "scene_inspector_overlay", None)
        toggle = getattr(overlay, "toggle", None)
        if callable(toggle):
            toggle()
        return True

    if key == optional_arcade.arcade.key.F11:
        if not bool(getattr(window, "show_debug", False)):
            return False
        from engine.tile_paint_mode import TilePaintState  # noqa: PLC0415

        state = getattr(window, "tile_paint_state", None)
        if not isinstance(state, TilePaintState):
            return False

        state.enabled = not bool(getattr(state, "enabled", False))
        if state.enabled and not str(getattr(state, "layer_id", "") or "").strip():
            sc = getattr(window, "scene_controller", None)
            scene_payload = getattr(sc, "_loaded_scene_data", None) if sc is not None else None
            tilemap_value = scene_payload.get("tilemap") if isinstance(scene_payload, dict) else None
            tilemap_payload: dict[str, Any] = tilemap_value if isinstance(tilemap_value, dict) else {}

            from engine.tile_paint_mode import cycle_layer_id  # noqa: PLC0415

            state.layer_id = cycle_layer_id(tile_layers=tilemap_payload.get("tile_layers") or [], current="", direction=1)
        return True

    if bool(getattr(window, "show_debug", False)) and not ui_blocks_input(controller) and optional_arcade.arcade.key.KEY_1 <= int(key) <= optional_arcade.arcade.key.KEY_9:
        slot = int(key) - int(optional_arcade.arcade.key.KEY_1) + 1

        from engine.tile_paint_mode import TilePaintState  # noqa: PLC0415

        tile_state = getattr(window, "tile_paint_state", None)
        if isinstance(tile_state, TilePaintState) and bool(getattr(tile_state, "enabled", False)):
            if modifiers & optional_arcade.arcade.key.MOD_ALT:
                current = int(getattr(tile_state, "tile_id", 0) or 0)
                slots = getattr(window, "tile_quick_slots", None)
                if not isinstance(slots, dict):
                    slots = {}
                    setattr(window, "tile_quick_slots", slots)
                slots[int(slot)] = int(current)
                print(f"TILE_SLOT_ASSIGN ok slot={slot} tile={int(current)}")
                return True

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

        from engine.entity_paint_mode import EntityPaintState  # noqa: PLC0415

        entity_state = getattr(window, "entity_paint_state", None)
        if isinstance(entity_state, EntityPaintState) and bool(getattr(entity_state, "enabled", False)):
            if modifiers & optional_arcade.arcade.key.MOD_ALT:
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

    if key == optional_arcade.arcade.key.F12:
        overlay = getattr(window, "scene_inspector_overlay", None)
        debug_active = bool(getattr(window, "show_debug", False)) or bool(getattr(overlay, "visible", False))
        if not debug_active:
            return False

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

    if key == optional_arcade.arcade.key.D and bool(getattr(window, "show_debug", False)) and (modifiers & optional_arcade.arcade.key.MOD_CTRL):
        from engine.entity_select_mode import (  # noqa: PLC0415
            EntitySelectState,
            get_duplicate_offset,
            other_authoring_modes_active,
            set_selection,
            selection_sorted_unique,
        )

        if other_authoring_modes_active(window):
            return False

        state = getattr(window, "entity_select_state", None)
        if not isinstance(state, EntitySelectState):
            return False

        selected_ids = selection_sorted_unique(list(getattr(state, "selected_ids", []) or []))
        if not selected_ids:
            print("ENTITY_DUPLICATE noop (none selected)")
            return True

        sc = getattr(window, "scene_controller", None)
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
                dup_entities_by_id: dict[str, dict[str, Any]] = {
                    str(e.get("id")): e for e in ents if isinstance(e, dict) and isinstance(e.get("id"), str)
                }
                dup_prefab_ids: list[str] = []
                for eid in new_ids:
                    ent = dup_entities_by_id.get(eid)
                    pid = ent.get("prefab_id") if isinstance(ent, dict) else None
                    if isinstance(pid, str) and pid.strip():
                        dup_prefab_ids.append(pid.strip())
                _recent_push_many(window, attr="prefab_recent", values=dup_prefab_ids, max_items=12)

        print(f"ENTITY_DUPLICATE ok count={len(new_ids)} dx={float(dx):.1f} dy={float(dy):.1f}")
        return True

    if key == optional_arcade.arcade.key.C and bool(getattr(window, "show_debug", False)) and (modifiers & optional_arcade.arcade.key.MOD_CTRL):
        from engine.entity_select_mode import EntitySelectState, other_authoring_modes_active, selection_sorted_unique  # noqa: PLC0415

        if other_authoring_modes_active(window) or ui_blocks_input(controller):
            return False

        state = getattr(window, "entity_select_state", None)
        if not isinstance(state, EntitySelectState):
            print("ENTITY_COPY noop reason=no_selection")
            return True

        selected_ids = selection_sorted_unique(list(getattr(state, "selected_ids", []) or []))
        if not selected_ids:
            print("ENTITY_COPY noop reason=no_selection")
            return True

        sc = getattr(window, "scene_controller", None)
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

    if key == optional_arcade.arcade.key.V and bool(getattr(window, "show_debug", False)) and (modifiers & optional_arcade.arcade.key.MOD_CTRL):
        from engine.entity_select_mode import EntitySelectState, other_authoring_modes_active, set_selection  # noqa: PLC0415

        if other_authoring_modes_active(window) or ui_blocks_input(controller):
            return False

        clip = getattr(window, "entity_clipboard", None)
        entities = clip.get("entities") if isinstance(clip, dict) else None
        if not isinstance(entities, list) or not entities:
            print("ENTITY_PASTE noop reason=empty_clipboard")
            return True

        sc = getattr(window, "scene_controller", None)
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
            except Exception:  # noqa: BLE001
                anchor_x, anchor_y = None, None
        if not (isinstance(anchor_x, (int, float)) and isinstance(anchor_y, (int, float))):
            finder = getattr(sc, "_find_player_sprite", None) if sc is not None else None
            try:
                player = finder() if callable(finder) else None
            except Exception:  # noqa: BLE001
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

        state = getattr(window, "entity_select_state", None)
        if isinstance(state, EntitySelectState):
            set_selection(window, state, pasted_ids, primary_id=pasted_primary)

        marker = getattr(window, "mark_scene_dirty", None)
        if callable(marker):
            marker("entity_select_paste")

        authored_fn = getattr(sc, "get_authored_scene_payload", None) if sc is not None else None
        authored_payload = authored_fn() if callable(authored_fn) else None
        if isinstance(authored_payload, dict):
            ents = authored_payload.get("entities")
            if isinstance(ents, list):
                pasted_entities_by_id: dict[str, dict[str, Any]] = {
                    str(e.get("id")): e for e in ents if isinstance(e, dict) and isinstance(e.get("id"), str)
                }
                pasted_prefab_ids: list[str] = []
                for eid in pasted_ids:
                    ent = pasted_entities_by_id.get(eid)
                    pid = ent.get("prefab_id") if isinstance(ent, dict) else None
                    if isinstance(pid, str) and pid.strip():
                        pasted_prefab_ids.append(pid.strip())
                _recent_push_many(window, attr="prefab_recent", values=pasted_prefab_ids, max_items=12)

        print(f"ENTITY_PASTE ok count={len(pasted_ids)} primary={pasted_primary}")
        return True

    if key in (optional_arcade.arcade.key.E, optional_arcade.arcade.key.H, optional_arcade.arcade.key.J) and bool(getattr(window, "show_debug", False)) and (modifiers & optional_arcade.arcade.key.MOD_CTRL):
        from engine.entity_select_mode import EntitySelectState, other_authoring_modes_active, selection_sorted_unique  # noqa: PLC0415

        if other_authoring_modes_active(window) or ui_blocks_input(controller):
            return False

        state = getattr(window, "entity_select_state", None)
        if not isinstance(state, EntitySelectState):
            print("ENTITY_TRANSFORM noop reason=no_selection")
            return True

        selected_ids = selection_sorted_unique(list(getattr(state, "selected_ids", []) or []))
        if not selected_ids:
            print("ENTITY_TRANSFORM noop reason=no_selection")
            return True

        sc = getattr(window, "scene_controller", None)
        transformer = getattr(sc, "debug_transform_entities_by_ids", None) if sc is not None else None
        if not callable(transformer):
            print("ENTITY_TRANSFORM noop reason=no_selection")
            return True

        if int(key) == int(optional_arcade.arcade.key.E):
            op = "rotate_cw_90"
            ok_prefix = "ENTITY_ROTATE"
            action = "rotate"
        elif int(key) == int(optional_arcade.arcade.key.H):
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

        count = int(
            transformer(
                selected_ids,
                op=op,
                snap_to_tile=bool(getattr(window, "entity_snap_to_tile", False)),
            )
            or 0
        )
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

    if key in (optional_arcade.arcade.key.DELETE, optional_arcade.arcade.key.BACKSPACE) and bool(getattr(window, "show_debug", False)):
        from engine.entity_select_mode import EntitySelectState, clear_drag, other_authoring_modes_active, set_selection  # noqa: PLC0415

        if not other_authoring_modes_active(window):
            state = getattr(window, "entity_select_state", None)
            selected_ids_raw = getattr(state, "selected_ids", None) if state is not None else None
            if isinstance(state, EntitySelectState) and isinstance(selected_ids_raw, list) and selected_ids_raw:
                sc = getattr(window, "scene_controller", None)
                remover = getattr(sc, "debug_remove_entity_by_id", None) if sc is not None else None
                removed_any = False
                if callable(remover):
                    pusher = getattr(window, "push_undo_frame", None)
                    if callable(pusher):
                        pusher("entity_select_delete")
                    for entity_id in sorted({str(i).strip() for i in selected_ids_raw if isinstance(i, str) and str(i).strip()}):
                        removed_any = bool(remover(entity_id)) or removed_any
                if removed_any:
                    marker = getattr(window, "mark_scene_dirty", None)
                    if callable(marker):
                        marker("entity_select_multi")
                set_selection(window, state, [])
                clear_drag(state)
                return True
        return False

    if key in (optional_arcade.arcade.key.UP, optional_arcade.arcade.key.DOWN, optional_arcade.arcade.key.LEFT, optional_arcade.arcade.key.RIGHT):
        overlay = getattr(window, "scene_inspector_overlay", None)
        debug_active = bool(getattr(window, "show_debug", False)) or bool(getattr(overlay, "visible", False))
        entity_state = getattr(window, "entity_paint_state", None)
        if bool(getattr(window, "show_debug", False)):
            from engine.entity_select_mode import EntitySelectState, other_authoring_modes_active  # noqa: PLC0415

            if not other_authoring_modes_active(window):
                sel_state = getattr(window, "entity_select_state", None)
                selected_ids_raw = getattr(sel_state, "selected_ids", None) if sel_state is not None else None
                if isinstance(sel_state, EntitySelectState) and isinstance(selected_ids_raw, list) and selected_ids_raw:
                    sc = getattr(window, "scene_controller", None)
                    mover = getattr(sc, "debug_move_entity_by_id", None) if sc is not None else None
                    finder = getattr(sc, "debug_find_sprite_by_entity_id", None) if sc is not None else None
                    if callable(mover) and callable(finder):
                        step = 8.0 if (modifiers & optional_arcade.arcade.key.MOD_SHIFT) else 1.0
                        dx = 0.0
                        dy = 0.0
                        if key == optional_arcade.arcade.key.LEFT:
                            dx = -step
                        elif key == optional_arcade.arcade.key.RIGHT:
                            dx = step
                        elif key == optional_arcade.arcade.key.UP:
                            dy = step
                        elif key == optional_arcade.arcade.key.DOWN:
                            dy = -step

                        pusher = getattr(window, "push_undo_frame", None)
                        if callable(pusher) and (dx or dy):
                            pusher("entity_select_nudge")

                        moved_any = False
                        for entity_id in sorted({str(i).strip() for i in selected_ids_raw if isinstance(i, str) and str(i).strip()}):
                            sprite = finder(entity_id)
                            if sprite is None:
                                continue
                            moved_any = (
                                bool(mover(entity_id, x=float(sprite.center_x) + dx, y=float(sprite.center_y) + dy)) or moved_any
                            )
                        if moved_any:
                            marker = getattr(window, "mark_scene_dirty", None)
                            if callable(marker):
                                marker("entity_select_multi")
                        return True
        if (
            debug_active
            and isinstance(entity_state, EntityPaintState)
            and bool(getattr(entity_state, "enabled", False))
            ):
            from engine.tooling_runtime.authoring_snippets import (  # noqa: PLC0415
                get_effective_hover_payload,
                get_scene_inspector_payload,
            )

            inspector_payload = get_scene_inspector_payload(window)
            effective_payload = get_effective_hover_payload(window, inspector_payload)
            hover_value = effective_payload.get("hover") if isinstance(effective_payload, dict) else None
            hover_payload: dict[str, Any] = hover_value if isinstance(hover_value, dict) else {}
            hover_id = hover_payload.get("id")
            if isinstance(hover_id, str) and hover_id.strip():
                sc = getattr(window, "scene_controller", None)
                finder = getattr(sc, "debug_find_sprite_by_entity_id", None) if sc is not None else None
                sprite = finder(hover_id) if callable(finder) else None
                if sprite is None:
                    return False

                step = 8.0 if (modifiers & optional_arcade.arcade.key.MOD_SHIFT) else 1.0
                dx = 0.0
                dy = 0.0
                if key == optional_arcade.arcade.key.LEFT:
                    dx = -step
                elif key == optional_arcade.arcade.key.RIGHT:
                    dx = step
                elif key == optional_arcade.arcade.key.UP:
                    dy = step
                elif key == optional_arcade.arcade.key.DOWN:
                    dy = -step

                mover = getattr(sc, "debug_move_entity_by_id", None)
                if callable(mover):
                    pusher = getattr(window, "push_undo_frame", None)
                    if callable(pusher) and (dx or dy):
                        pusher("entity_paint_nudge")
                    if mover(hover_id, x=float(sprite.center_x) + dx, y=float(sprite.center_y) + dy):
                        entity_state.moves += 1
                        entity_state.last_snippet = f"ENTITY_MOVE --id {hover_id} --x {float(sprite.center_x + dx):.1f} --y {float(sprite.center_y + dy):.1f}"
                        marker = getattr(window, "mark_scene_dirty", None)
                        if callable(marker):
                            marker("entity_paint")
                        return True
        # Debug is off, or no hover: fall through to selection nudge bindings.
        if debug_active and getattr(window, "authoring_selected_entity_id", None):
            if modifiers & optional_arcade.arcade.key.MOD_CTRL:
                step = 32.0
            elif modifiers & optional_arcade.arcade.key.MOD_SHIFT:
                step = 1.0
            else:
                step = 8.0

            dx = 0.0
            dy = 0.0
            if key == optional_arcade.arcade.key.LEFT:
                dx = -step
            elif key == optional_arcade.arcade.key.RIGHT:
                dx = step
            elif key == optional_arcade.arcade.key.UP:
                dy = step
            elif key == optional_arcade.arcade.key.DOWN:
                dy = -step

            from engine.tooling_runtime.authoring_snippets import nudge_selected_entity  # noqa: PLC0415

            if nudge_selected_entity(window, dx=dx, dy=dy):
                return True
        # Debug is off, or no selection: fall through to normal bindings.

    if key == optional_arcade.arcade.key.F9:
        overlay = getattr(window, "scene_inspector_overlay", None)
        debug_active = bool(getattr(window, "show_debug", False)) or bool(getattr(overlay, "visible", False))

        if debug_active:
            from engine.tooling_runtime.authoring_snippets import (  # noqa: PLC0415
                build_hover_pos_snippet,
                build_player_pos_snippet,
                get_effective_hover_payload,
                get_scene_inspector_payload,
            )
            from engine.tooling_runtime.clipboard import try_copy_to_clipboard  # noqa: PLC0415

            inspector_payload = get_scene_inspector_payload(window)
            effective_payload = get_effective_hover_payload(window, inspector_payload)
            if modifiers & (optional_arcade.arcade.key.MOD_SHIFT | optional_arcade.arcade.key.MOD_CTRL):
                snippet = build_hover_pos_snippet(effective_payload)
            else:
                snippet = build_player_pos_snippet(effective_payload)

            print(snippet)
            try_copy_to_clipboard(snippet)
            return True

        new_state = window._toggle_paused_state()
        window.console_log(f"Paused = {new_state}")
        return True

    if key == optional_arcade.arcade.key.F3:
        window.show_debug = not window.show_debug
        controller._log_debug(f"[Mesh][Debug] show_debug = {window.show_debug}")
        return True

    if key == optional_arcade.arcade.key.F4:
        # Toggle Editor Mode
        window.editor_controller.toggle()
        return True

    if key == optional_arcade.arcade.key.F6:
        # Play From Here (editor-only)
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

    if key == optional_arcade.arcade.key.F7:
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

    if key == optional_arcade.arcade.key.F5:
        # Quick Save (debug-friendly)
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

    # Editor Input Handling
    if window.editor_controller.active:
        # Undo/Redo
        if modifiers & optional_arcade.arcade.key.MOD_CTRL:
            if key == optional_arcade.arcade.key.Z:
                window.editor_controller.undo_last()
                return True
            if key == optional_arcade.arcade.key.Y or (key == optional_arcade.arcade.key.Z and (modifiers & optional_arcade.arcade.key.MOD_SHIFT)):
                window.editor_controller.redo_last()
                return True

        if window.editor_controller.handle_input(key, modifiers):
            return True

    manager = getattr(controller, "manager", None)
    press = getattr(manager, "press", None) if manager is not None else None
    if callable(press):
        press(key)
    keys = getattr(controller, "_keys", None)
    if isinstance(keys, set):
        keys.add(key)
    return False


def handle_key_release(controller: "InputController", key: int, modifiers: int) -> bool:  # noqa: ARG001
    manager = getattr(controller, "manager", None)
    release = getattr(manager, "release", None) if manager is not None else None
    if callable(release):
        release(key)
    keys = getattr(controller, "_keys", None)
    if isinstance(keys, set):
        keys.discard(key)
    return False


def handle_mouse_motion(controller: "InputController", x: float, y: float, dx: float, dy: float) -> None:  # noqa: ARG001
    controller._mouse_x = float(x)
    controller._mouse_y = float(y)
    # Back-compat for overlay providers that read window._mouse_x/_mouse_y.
    setattr(controller.window, "_mouse_x", float(x))
    setattr(controller.window, "_mouse_y", float(y))

    # Route to editor for menu bar and context menu hover
    editor_controller = getattr(controller.window, "editor_controller", None)
    if editor_controller is not None and getattr(editor_controller, "active", False):
        from engine.editor_runtime.input import handle_menu_bar_motion, handle_context_menu_motion  # noqa: PLC0415
        from engine.editor_runtime.hover_detection import update_hover_state  # noqa: PLC0415

        handle_menu_bar_motion(editor_controller, x, y)
        handle_context_menu_motion(editor_controller, x, y)

        # Update hover highlight state for all UI elements and entities
        window_w = getattr(controller.window, "width", 1280)
        window_h = getattr(controller.window, "height", 720)
        update_hover_state(editor_controller, x, y, window_w, window_h)

        # Track mouse position for cursor hint
        set_mouse_pos = getattr(editor_controller, "set_last_mouse_pos", None)
        if callable(set_mouse_pos):
            set_mouse_pos(x, y)

        # Apply cursor affordance (editor-only)
        try:
            from engine.editor.editor_cursor_apply import apply_editor_cursor  # noqa: PLC0415

            get_kind = getattr(editor_controller, "get_cursor_hint_kind", None)
            if callable(get_kind):
                cursor_kind = get_kind(window_w, window_h)
                apply_editor_cursor(controller.window, cursor_kind)
        except Exception:  # noqa: BLE001
            pass


def handle_mouse_drag(
    controller: "InputController",
    x: float,
    y: float,
    dx: float,
    dy: float,
    buttons: int,
    modifiers: int,
) -> None:
    controller._mouse_x = float(x)
    controller._mouse_y = float(y)
    setattr(controller.window, "_mouse_x", float(x))
    setattr(controller.window, "_mouse_y", float(y))
    try:
        setattr(controller.window, "_debug_last_modifiers", int(modifiers))
    except Exception:  # noqa: BLE001
        pass
    if controller.window.editor_controller.active:
        if controller.window.editor_controller.handle_mouse_drag(x, y, dx, dy, buttons, modifiers):
            return
    window = controller.window
    if bool(getattr(window, "show_debug", False)) and getattr(window, "command_palette_enabled", False) is True:
        return
    from engine.capture_mode import CaptureState  # noqa: PLC0415

    capture_state = getattr(window, "capture_state", None)
    if isinstance(capture_state, CaptureState) and bool(getattr(window, "show_debug", False)) and bool(getattr(capture_state, "enabled", False)):
        if not (int(buttons) & int(optional_arcade.arcade.MOUSE_BUTTON_LEFT)):
            return
        sc = getattr(window, "scene_controller", None)
        instance = getattr(sc, "tilemap_instance", None) if sc is not None else None
        if instance is None:
            return
        map_w, map_h = getattr(instance, "map_size", (0, 0))
        tile_w, tile_h = getattr(instance, "tile_size", (0, 0))
        try:
            world_x, world_y = window.screen_to_world(float(x), float(y))
        except Exception:  # noqa: BLE001
            return
        from engine.tile_paint_mode import world_to_tile  # noqa: PLC0415

        hit = world_to_tile(
            map_width=int(map_w),
            map_height=int(map_h),
            tile_width=int(tile_w),
            tile_height=int(tile_h),
            world_x=float(world_x),
            world_y=float(world_y),
        )
        if hit is None:
            return
        anchor = getattr(capture_state, "drag_anchor", None)
        if anchor is None:
            capture_state.drag_anchor = (int(hit[0]), int(hit[1]))
            anchor = capture_state.drag_anchor
        if anchor is None:
            return
        ax, ay = anchor
        from engine.capture_mode import normalize_rect  # noqa: PLC0415

        capture_state.rect = normalize_rect(int(ax), int(ay), int(hit[0]), int(hit[1]))
        return

    from engine.tile_paint_mode import TilePaintState  # noqa: PLC0415

    tile_paint_state = getattr(window, "tile_paint_state", None)
    if (
        bool(getattr(window, "show_debug", False))
        and isinstance(tile_paint_state, TilePaintState)
        and bool(getattr(tile_paint_state, "enabled", False))
        and bool(getattr(tile_paint_state, "stroke_active", False))
    ):
        if not (int(buttons) & int(getattr(tile_paint_state, "stroke_button", 0) or 0)):
            return
        sc = getattr(window, "scene_controller", None)
        instance = getattr(sc, "tilemap_instance", None) if sc is not None else None
        if instance is None:
            return
        map_w, map_h = getattr(instance, "map_size", (0, 0))
        tile_w, tile_h = getattr(instance, "tile_size", (0, 0))
        if not all(isinstance(v, int) for v in (map_w, map_h, tile_w, tile_h)):
            return
        try:
            world_x, world_y = window.screen_to_world(float(x), float(y))
        except Exception:  # noqa: BLE001
            return
        from engine.tile_paint_mode import world_to_tile  # noqa: PLC0415

        hit = world_to_tile(
            map_width=int(map_w),
            map_height=int(map_h),
            tile_width=int(tile_w),
            tile_height=int(tile_h),
            world_x=float(world_x),
            world_y=float(world_y),
        )
        if hit is None:
            return
        tx, ty = hit
        tile_paint_state.stroke_last_hit = (int(tx), int(ty))
        if str(getattr(tile_paint_state, "stroke_tool", "") or "") == "brush":
            tile_paint_state.stroke_coords.add((int(tx), int(ty)))
        return

    if bool(getattr(window, "show_debug", False)) and (int(buttons) & int(optional_arcade.arcade.MOUSE_BUTTON_LEFT)):
        from engine.entity_select_mode import (  # noqa: PLC0415
            EntitySelectState,
            other_authoring_modes_active,
            selection_sorted_unique,
            snap_world_to_tile_center,
            update_drag_rect,
        )

        if not other_authoring_modes_active(window):
            state = getattr(window, "entity_select_state", None)
            if not (isinstance(state, EntitySelectState) and bool(getattr(state, "dragging", False))):
                return
            try:
                world_x, world_y = window.screen_to_world(float(x), float(y))
            except Exception:  # noqa: BLE001
                return

            if str(getattr(state, "drag_mode", "") or "") == "marquee":
                update_drag_rect(state, world_x=float(world_x), world_y=float(world_y))
                return

            if str(getattr(state, "drag_mode", "") or "") != "move":
                return

            selected_ids = selection_sorted_unique(list(getattr(state, "selected_ids", []) or []))
            primary_id = str(getattr(state, "primary_id", "") or "").strip() or (selected_ids[0] if selected_ids else "")
            if not selected_ids or not primary_id:
                return

            sc = getattr(window, "scene_controller", None)
            mover = getattr(sc, "debug_move_entity_by_id", None) if sc is not None else None
            finder = getattr(sc, "debug_find_sprite_by_entity_id", None) if sc is not None else None
            if not (callable(mover) and callable(finder)):
                return

            if getattr(state, "drag_start_positions", None) is None:
                start_positions: dict[str, tuple[float, float]] = {}
                for entity_id in selected_ids:
                    sprite = finder(entity_id)
                    if sprite is None:
                        continue
                    start_positions[entity_id] = (float(sprite.center_x), float(sprite.center_y))
                state.drag_start_positions = start_positions

            start_positions = getattr(state, "drag_start_positions", None) or {}
            primary_start = start_positions.get(primary_id)
            if primary_start is None:
                sprite = finder(primary_id)
                if sprite is None:
                    return
                primary_start = (float(sprite.center_x), float(sprite.center_y))
                start_positions[primary_id] = primary_start

            ox, oy = getattr(state, "drag_click_offset", None) or (0.0, 0.0)
            desired_primary_x = float(world_x) - float(ox)
            desired_primary_y = float(world_y) - float(oy)

            new_primary_x = desired_primary_x
            new_primary_y = desired_primary_y
            if bool(getattr(window, "entity_snap_to_tile", False)):
                snapped = snap_world_to_tile_center(window, world_x=float(desired_primary_x), world_y=float(desired_primary_y))
                if snapped is not None:
                    new_primary_x, new_primary_y = snapped

            dx = float(new_primary_x) - float(primary_start[0])
            dy = float(new_primary_y) - float(primary_start[1])

            if (dx or dy) and not bool(getattr(state, "drag_undo_pushed", False)):
                pusher = getattr(window, "push_undo_frame", None)
                if callable(pusher):
                    pusher("entity_select_drag")
                state.drag_undo_pushed = True

            moved_any = False
            for entity_id in selected_ids:
                start = start_positions.get(entity_id)
                if start is None:
                    sprite = finder(entity_id)
                    if sprite is None:
                        continue
                    start = (float(sprite.center_x), float(sprite.center_y))
                    start_positions[entity_id] = start
                moved_any = bool(mover(entity_id, x=float(start[0]) + dx, y=float(start[1]) + dy)) or moved_any

            if moved_any and not bool(getattr(state, "drag_dirty_marked", False)):
                marker = getattr(window, "mark_scene_dirty", None)
                if callable(marker):
                    marker("entity_select_multi")
                state.drag_dirty_marked = True
            return


def handle_mouse_press(controller: "InputController", x: float, y: float, button: int, modifiers: int) -> bool:
    from engine.palette_mode import get_state
    if get_state().enabled:
        return True

    if controller.window.editor_controller.active:
        if controller.window.editor_controller.handle_mouse_click(x, y, button, modifiers):
            return True

    window = controller.window
    if bool(getattr(window, "show_debug", False)) and getattr(window, "command_palette_enabled", False) is True:
        return True
    # Ensure hover providers see the click location deterministically.
    try:
        setattr(window, "_mouse_x", float(x))
        setattr(window, "_mouse_y", float(y))
        setattr(window, "_debug_last_modifiers", int(modifiers))
    except Exception:  # noqa: BLE001
        pass
    from engine.capture_mode import CaptureState  # noqa: PLC0415

    capture_state = getattr(window, "capture_state", None)
    if isinstance(capture_state, CaptureState) and bool(getattr(window, "show_debug", False)) and bool(getattr(capture_state, "enabled", False)):
        if int(button) == int(optional_arcade.arcade.MOUSE_BUTTON_LEFT):
            sc = getattr(window, "scene_controller", None)
            instance = getattr(sc, "tilemap_instance", None) if sc is not None else None
            if instance is None:
                return True
            map_w, map_h = getattr(instance, "map_size", (0, 0))
            tile_w, tile_h = getattr(instance, "tile_size", (0, 0))
            try:
                world_x, world_y = window.screen_to_world(float(x), float(y))
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
            if hit is None:
                return True
            capture_state.drag_anchor = (int(hit[0]), int(hit[1]))
            from engine.capture_mode import normalize_rect  # noqa: PLC0415

            capture_state.rect = normalize_rect(int(hit[0]), int(hit[1]), int(hit[0]), int(hit[1]))
        return True

    window = controller.window
    from engine.entity_paint_mode import EntityPaintState  # noqa: PLC0415

    entity_state = getattr(window, "entity_paint_state", None)
    if isinstance(entity_state, EntityPaintState) and bool(getattr(window, "show_debug", False)) and bool(getattr(entity_state, "enabled", False)):
        # Ensure hover providers see the click location deterministically.
        setattr(window, "_mouse_x", float(x))
        setattr(window, "_mouse_y", float(y))

        sc = getattr(window, "scene_controller", None)
        scene_path = str(getattr(sc, "current_scene_path", "") or "").strip()
        authored = getattr(sc, "get_authored_scene_payload", None)
        payload = authored() if callable(authored) else getattr(sc, "_loaded_scene_data", None)

        if not isinstance(payload, dict) or sc is None or not scene_path:
            return True

        try:
            world_x, world_y = window.screen_to_world(float(x), float(y))
        except Exception:  # noqa: BLE001
            return True

        hover_id: str | None = None
        hover_prefab: str | None = None
        try:
            from engine.tooling_runtime.authoring_snippets import (  # noqa: PLC0415
                get_effective_hover_payload,
                get_scene_inspector_payload,
            )

            inspector = get_scene_inspector_payload(window)
            inspector = get_effective_hover_payload(window, inspector)
            hover = inspector.get("hover") if isinstance(inspector, dict) and isinstance(inspector.get("hover"), dict) else None
            if isinstance(hover, dict):
                hid = hover.get("id")
                if isinstance(hid, str) and hid.strip():
                    hover_id = hid.strip()
                hpid = hover.get("prefab_id")
                if isinstance(hpid, str) and hpid.strip():
                    hover_prefab = hpid.strip()
        except Exception:  # noqa: BLE001
            hover_id = None
            hover_prefab = None

        snap = bool(getattr(entity_state, "snap_to_tile", False))
        if snap:
            instance = getattr(sc, "tilemap_instance", None)
            map_w = map_h = tile_w = tile_h = None
            if instance is not None:
                mw, mh = getattr(instance, "map_size", (None, None))
                tw, th = getattr(instance, "tile_size", (None, None))
                if (
                    isinstance(mw, int)
                    and isinstance(mh, int)
                    and isinstance(tw, int)
                    and isinstance(th, int)
                    and mw > 0
                    and mh > 0
                    and tw > 0
                    and th > 0
                ):
                    map_w, map_h, tile_w, tile_h = mw, mh, tw, th
            if map_w is None:
                tilemap = payload.get("tilemap") if isinstance(payload.get("tilemap"), dict) else None
                mw = tilemap.get("width") if isinstance(tilemap, dict) else None
                mh = tilemap.get("height") if isinstance(tilemap, dict) else None
                tw = tilemap.get("tilewidth") if isinstance(tilemap, dict) else None
                th = tilemap.get("tileheight") if isinstance(tilemap, dict) else None
                if (
                    isinstance(mw, int)
                    and isinstance(mh, int)
                    and isinstance(tw, int)
                    and isinstance(th, int)
                    and mw > 0
                    and mh > 0
                    and tw > 0
                    and th > 0
                ):
                    map_w, map_h, tile_w, tile_h = mw, mh, tw, th
            if map_w is not None and map_h is not None and tile_w is not None and tile_h is not None:
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
                    world_x = (float(tx) + 0.5) * float(tile_w)
                    world_y = (float(ty) + 0.5) * float(tile_h)

        if int(button) == int(optional_arcade.arcade.MOUSE_BUTTON_RIGHT):
            if hover_id:
                remover = getattr(sc, "debug_remove_entity_by_id", None)
                pusher = getattr(window, "push_undo_frame", None)
                if callable(pusher):
                    pusher("entity_paint_remove")
                if callable(remover) and remover(hover_id):
                    entity_state.removes += 1
                    entity_state.last_snippet = f"ENTITY_REMOVE --id {hover_id}"
                    marker = getattr(window, "mark_scene_dirty", None)
                    if callable(marker):
                        marker("entity_paint")
            return True

        # Left click
        if hover_id:
            if modifiers & optional_arcade.arcade.key.MOD_CTRL:
                mover = getattr(sc, "debug_move_entity_by_id", None)
                pusher = getattr(window, "push_undo_frame", None)
                if callable(pusher):
                    pusher("entity_paint_move")
                if callable(mover) and mover(hover_id, x=float(world_x), y=float(world_y)):
                    entity_state.moves += 1
                    entity_state.last_snippet = f"ENTITY_MOVE --id {hover_id} --x {float(world_x):.1f} --y {float(world_y):.1f}"
                    marker = getattr(window, "mark_scene_dirty", None)
                    if callable(marker):
                        marker("entity_paint")
            return True

        from engine.entity_paint_mode import build_add_snippet, get_selected_prefab_id, make_entity_id  # noqa: PLC0415

        prefab_id = get_selected_prefab_id(entity_state)
        if not isinstance(prefab_id, str) or not prefab_id.strip():
            return True
        prefab_id = prefab_id.strip()
        entity_id = make_entity_id(scene_path, prefab_id, float(world_x), float(world_y))
        entity_payload = {
            "id": entity_id,
            "prefab_id": prefab_id,
            "x": float(world_x),
            "y": float(world_y),
            "layer": "entities",
        }
        adder = getattr(sc, "debug_add_entity_payload", None)
        pusher = getattr(window, "push_undo_frame", None)
        if callable(pusher):
            pusher("entity_paint_add")
        if callable(adder) and adder(entity_payload):
            entity_state.adds += 1
            entity_state.last_snippet = build_add_snippet(prefab_id=prefab_id, entity_id=entity_id, x=float(world_x), y=float(world_y))
            marker = getattr(window, "mark_scene_dirty", None)
            if callable(marker):
                marker("entity_paint")
            _recent_push_str(window, attr="prefab_recent", value=prefab_id, max_items=12)
        return True

    state = getattr(window, "tile_paint_state", None)
    if bool(getattr(window, "show_debug", False)) and bool(getattr(state, "enabled", False)):
        from engine.tile_paint_mode import (  # noqa: PLC0415
            TilePaintState,
            compute_tile_paint_tool,
            peek_tile_value,
            world_to_tile,
        )

        if not isinstance(state, TilePaintState):
            return True

        sc = getattr(window, "scene_controller", None)
        instance = getattr(sc, "tilemap_instance", None) if sc is not None else None
        payloads: list[dict] = []
        iter_payloads = getattr(sc, "_debug_iter_authoring_payloads", None) if sc is not None else None
        if callable(iter_payloads):
            try:
                payloads = [p for p in iter_payloads() if isinstance(p, dict)]
            except Exception:  # noqa: BLE001
                payloads = []
        if not payloads and sc is not None and isinstance(getattr(sc, "_loaded_scene_data", None), dict):
            payloads = [sc._loaded_scene_data]

        if not payloads or instance is None:
            if int(button) == int(optional_arcade.arcade.MOUSE_BUTTON_LEFT) and (modifiers & optional_arcade.arcade.key.MOD_SHIFT) and not (modifiers & optional_arcade.arcade.key.MOD_CTRL):
                print("TILE_PICK noop reason=no_tilemap")
            return True

        map_w, map_h = getattr(instance, "map_size", (0, 0))
        tile_w, tile_h = getattr(instance, "tile_size", (0, 0))
        if not all(isinstance(v, int) for v in (map_w, map_h, tile_w, tile_h)):
            if int(button) == int(optional_arcade.arcade.MOUSE_BUTTON_LEFT) and (modifiers & optional_arcade.arcade.key.MOD_SHIFT) and not (modifiers & optional_arcade.arcade.key.MOD_CTRL):
                print("TILE_PICK noop reason=no_tilemap")
            return True

        layer_id = str(getattr(state, "layer_id", "") or "").strip()
        if not layer_id:
            return True

        world_x, world_y = window.screen_to_world(float(x), float(y))
        hit = world_to_tile(
            map_width=int(map_w),
            map_height=int(map_h),
            tile_width=int(tile_w),
            tile_height=int(tile_h),
            world_x=float(world_x),
            world_y=float(world_y),
        )
        if hit is None:
            if int(button) == int(optional_arcade.arcade.MOUSE_BUTTON_LEFT) and (modifiers & optional_arcade.arcade.key.MOD_SHIFT) and not (modifiers & optional_arcade.arcade.key.MOD_CTRL):
                print("TILE_PICK noop reason=out_of_bounds")
            return True

        tx, ty = hit
        tool = compute_tile_paint_tool(
            shift=bool(modifiers & optional_arcade.arcade.key.MOD_SHIFT),
            ctrl=bool(modifiers & optional_arcade.arcade.key.MOD_CTRL),
            alt=bool(modifiers & optional_arcade.arcade.key.MOD_ALT),
        )

        if tool == "pick" and int(button) == int(optional_arcade.arcade.MOUSE_BUTTON_LEFT):
            v = peek_tile_value(payloads[0], layer_id=layer_id, tx=int(tx), ty=int(ty), map_width=int(map_w), map_height=int(map_h))
            if v is None:
                print("TILE_PICK noop reason=layer_missing")
                return True
            state.tile_id = int(v)
            _recent_push_int(window, attr="tile_recent", value=int(v), max_items=12)
            print(f"TILE_PICK ok tile={int(v)} layer={layer_id}")
            return True

        state.stroke_active = True
        state.stroke_tool = str(tool or "brush")
        state.stroke_button = int(button)
        state.stroke_anchor = (int(tx), int(ty))
        state.stroke_last_hit = (int(tx), int(ty))
        state.stroke_coords.clear()
        if state.stroke_tool == "brush":
            state.stroke_coords.add((int(tx), int(ty)))
        return True

    # Debug-only universal entity selection (when no other authoring mode is active).
    if bool(getattr(window, "show_debug", False)) and int(button) == int(optional_arcade.arcade.MOUSE_BUTTON_LEFT):
        from engine.entity_select_mode import (  # noqa: PLC0415
            EntitySelectState,
            clear_drag,
            add_selected,
            other_authoring_modes_active,
            selection_sorted_unique,
            set_selection,
            toggle_selected,
        )

        if not other_authoring_modes_active(window):
            state = getattr(window, "entity_select_state", None)
            if isinstance(state, EntitySelectState):
                from engine.tooling_runtime.authoring_snippets import get_scene_inspector_payload  # noqa: PLC0415

                inspector_payload_obj = get_scene_inspector_payload(window)
                inspector_payload: dict[str, Any] = inspector_payload_obj if isinstance(inspector_payload_obj, dict) else {}
                hover_value = inspector_payload.get("hover")
                hover_payload: dict[str, Any] = hover_value if isinstance(hover_value, dict) else {}
                hover_id = hover_payload.get("id")
                hover_prefab = hover_payload.get("prefab_id")

                if isinstance(hover_id, str) and hover_id.strip():
                    hover_id = hover_id.strip()
                    state.selected_prefab_id = str(hover_prefab or "").strip()

                    existing = selection_sorted_unique(list(getattr(state, "selected_ids", []) or []))
                    if modifiers & optional_arcade.arcade.key.MOD_SHIFT:
                        toggle_selected(window, state, hover_id, make_primary=True)
                    elif modifiers & optional_arcade.arcade.key.MOD_CTRL:
                        add_selected(window, state, hover_id, make_primary=True)
                    else:
                        if hover_id in existing:
                            set_selection(window, state, existing, primary_id=hover_id)
                        else:
                            set_selection(window, state, [hover_id], primary_id=hover_id)

                    try:
                        world_x, world_y = window.screen_to_world(float(x), float(y))
                    except Exception:  # noqa: BLE001
                        clear_drag(state)
                        return True

                    selected_ids = selection_sorted_unique(list(getattr(state, "selected_ids", []) or []))
                    if hover_id not in selected_ids:
                        clear_drag(state)
                        return True

                    sc = getattr(window, "scene_controller", None)
                    finder = getattr(sc, "debug_find_sprite_by_entity_id", None) if sc is not None else None
                    if not callable(finder):
                        clear_drag(state)
                        return True

                    primary_sprite = finder(hover_id)
                    if primary_sprite is None:
                        clear_drag(state)
                        return True

                    state.dragging = True
                    state.drag_mode = "move"
                    state.drag_dirty_marked = False
                    state.drag_undo_pushed = False
                    state.drag_anchor_world = (float(world_x), float(world_y))
                    state.primary_id = hover_id
                    setattr(window, "authoring_selected_entity_id", hover_id)

                    start_positions: dict[str, tuple[float, float]] = {}
                    for entity_id in selected_ids:
                        sprite = finder(entity_id)
                        if sprite is None:
                            continue
                        start_positions[entity_id] = (float(sprite.center_x), float(sprite.center_y))
                    state.drag_start_positions = start_positions

                    px0, py0 = float(primary_sprite.center_x), float(primary_sprite.center_y)
                    state.drag_click_offset = (float(world_x) - px0, float(world_y) - py0)
                else:
                    try:
                        world_x, world_y = window.screen_to_world(float(x), float(y))
                    except Exception:  # noqa: BLE001
                        clear_drag(state)
                        return True
                    state.dragging = True
                    state.drag_mode = "marquee"
                    state.drag_dirty_marked = False
                    state.drag_undo_pushed = False
                    state.drag_anchor_world = (float(world_x), float(world_y))
                    state.drag_rect_world = (float(world_x), float(world_y), float(world_x), float(world_y))
                    state.drag_rect_moved = False
                return True

    return False


def handle_mouse_release(controller: "InputController", x: float, y: float, button: int, modifiers: int) -> bool:
    if controller.window.editor_controller.active:
        if controller.window.editor_controller.handle_mouse_release(x, y, button, modifiers):
            return True
    window = controller.window
    try:
        setattr(window, "_debug_last_modifiers", int(modifiers))
    except Exception:  # noqa: BLE001
        pass
    if bool(getattr(window, "show_debug", False)) and getattr(window, "command_palette_enabled", False) is True:
        return True
    from engine.capture_mode import CaptureState  # noqa: PLC0415

    capture_state = getattr(window, "capture_state", None)
    if isinstance(capture_state, CaptureState) and bool(getattr(window, "show_debug", False)) and bool(getattr(capture_state, "enabled", False)):
        if int(button) == int(optional_arcade.arcade.MOUSE_BUTTON_LEFT):
            capture_state.drag_anchor = None
        return True

    from engine.tile_paint_mode import TilePaintState  # noqa: PLC0415

    state = getattr(window, "tile_paint_state", None)
    if (
        bool(getattr(window, "show_debug", False))
        and isinstance(state, TilePaintState)
        and bool(getattr(state, "enabled", False))
        and bool(getattr(state, "stroke_active", False))
    ):
        if int(button) != int(getattr(state, "stroke_button", 0) or 0):
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
        iter_payloads = getattr(sc, "_debug_iter_authoring_payloads", None) if sc is not None else None
        if callable(iter_payloads):
            try:
                payloads = [p for p in iter_payloads() if isinstance(p, dict)]
            except Exception:  # noqa: BLE001
                payloads = []
        if not payloads and sc is not None and isinstance(getattr(sc, "_loaded_scene_data", None), dict):
            payloads = [sc._loaded_scene_data]

        tool = str(getattr(state, "stroke_tool", "") or "brush")
        layer_id = str(getattr(state, "layer_id", "") or "").strip()
        desired_tile = 0 if int(button) == int(optional_arcade.arcade.MOUSE_BUTTON_RIGHT) else int(getattr(state, "tile_id", 0) or 0)

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
                    if int(button) == int(optional_arcade.arcade.MOUSE_BUTTON_RIGHT):
                        changed_any = apply_erase(payload, layer_id=layer_id, tx=int(cx), ty=int(cy), map_width=int(map_w), map_height=int(map_h)) or changed_any
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
        except Exception:  # noqa: BLE001
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
            _recent_push_int(window, attr="tile_recent", value=int(desired_tile), max_items=12)
            print(f"TILE_STROKE ok tool={tool} count={len(changed_coords)} layer={layer_id} tile={int(desired_tile)}")

        state.stroke_active = False
        state.stroke_anchor = None
        state.stroke_last_hit = None
        state.stroke_coords.clear()
        return True
    if bool(getattr(window, "show_debug", False)) and int(button) == int(optional_arcade.arcade.MOUSE_BUTTON_LEFT):
        from engine.entity_select_mode import EntitySelectState, clear_drag, iter_entity_ids_in_world_rect, other_authoring_modes_active, selection_sorted_unique, set_selection  # noqa: PLC0415

        if not other_authoring_modes_active(window):
            state = getattr(window, "entity_select_state", None)
            if isinstance(state, EntitySelectState) and bool(getattr(state, "dragging", False)):
                mode = str(getattr(state, "drag_mode", "") or "")
                if mode == "marquee":
                    moved = bool(getattr(state, "drag_rect_moved", False))
                    rect = getattr(state, "drag_rect_world", None)
                    if moved and isinstance(rect, tuple) and len(rect) == 4:
                        ids_in_rect = iter_entity_ids_in_world_rect(window, rect)
                        current = selection_sorted_unique(list(getattr(state, "selected_ids", []) or []))
                        if modifiers & optional_arcade.arcade.key.MOD_SHIFT:
                            out = selection_sorted_unique(current + ids_in_rect)
                        elif modifiers & optional_arcade.arcade.key.MOD_CTRL:
                            out = selection_sorted_unique([i for i in current if i not in set(ids_in_rect)])
                        else:
                            out = ids_in_rect
                        set_selection(window, state, out)
                    else:
                        # Click empty: clear selection unless Shift is held.
                        if not (modifiers & optional_arcade.arcade.key.MOD_SHIFT):
                            set_selection(window, state, [])
                clear_drag(state)
                return True
    return False


def handle_mouse_scroll(controller: "InputController", x: float, y: float, scroll_x: float, scroll_y: float) -> bool:  # noqa: ARG001
    window = controller.window
    modifiers = int(getattr(window, "_debug_last_modifiers", 0) or 0)
    from engine.capture_mode import CaptureState  # noqa: PLC0415

    capture_state = getattr(window, "capture_state", None)
    if isinstance(capture_state, CaptureState) and bool(getattr(window, "show_debug", False)) and bool(getattr(capture_state, "enabled", False)):
        delta = int(1 if float(scroll_y) > 0 else (-1 if float(scroll_y) < 0 else 0))
        if delta == 0:
            return True

        sc = getattr(window, "scene_controller", None)
        payload = getattr(sc, "_loaded_scene_data", None) if sc is not None else None
        if not isinstance(payload, dict):
            return True

        # Ctrl+wheel cycles selected layer.
        if modifiers & optional_arcade.arcade.key.MOD_CTRL:
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
                    world_x, world_y = window.screen_to_world(float(x), float(y))
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

    from engine.entity_paint_mode import EntityPaintState  # noqa: PLC0415

    entity_state = getattr(window, "entity_paint_state", None)
    if isinstance(entity_state, EntityPaintState) and bool(getattr(window, "show_debug", False)) and bool(getattr(entity_state, "enabled", False)):
        delta = int(1 if float(scroll_y) > 0 else (-1 if float(scroll_y) < 0 else 0))
        if delta == 0:
            return True
        if modifiers & optional_arcade.arcade.key.MOD_SHIFT:
            from engine.entity_paint_mode import cycle_filter_mode  # noqa: PLC0415

            cycle_filter_mode(entity_state, direction=delta)
            return True
        if modifiers & optional_arcade.arcade.key.MOD_CTRL:
            # Ctrl+wheel arms/disarms snapping deterministically.
            entity_state.snap_to_tile = bool(delta > 0)
            return True

        from engine.entity_paint_mode import cycle_selected_prefab  # noqa: PLC0415

        cycle_selected_prefab(entity_state, direction=delta)
        return True

    from engine.tile_paint_mode import TilePaintState  # noqa: PLC0415

    state = getattr(window, "tile_paint_state", None)
    if not (bool(getattr(window, "show_debug", False)) and isinstance(state, TilePaintState) and bool(getattr(state, "enabled", False))):
        return False

    delta = int(1 if float(scroll_y) > 0 else (-1 if float(scroll_y) < 0 else 0))
    if delta == 0:
        return True

    if modifiers & optional_arcade.arcade.key.MOD_SHIFT:
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


def handle_text(controller: "InputController", text: str) -> None:
    window = controller.window
    if bool(getattr(window, "show_debug", False)) and getattr(window, "command_palette_enabled", False) is True:
        if bool(getattr(window, "command_palette_prompt_active", False)):
            prompt_kind = str(getattr(window, "command_palette_prompt_kind", "text") or "text").strip().lower()
            attr = "command_palette_prompt_query" if prompt_kind == "pick" else "command_palette_prompt_text"
            t = str(getattr(window, attr, "") or "")
            for ch in str(text or ""):
                if ch in ("\n", "\r"):
                    continue
                if ch.isprintable():
                    t += ch
            if len(t) > 200:
                t = t[-200:]
            setattr(window, attr, t)
            return

        q = str(getattr(window, "command_palette_query", "") or "")
        for ch in str(text or ""):
            if ch.isalnum() or ch == " ":
                q += ch
        if len(q) > 80:
            q = q[-80:]
        window.command_palette_query = q
        window.command_palette_index = 0
        return
    if window.console_controller.active:
        # Filter out control characters (like backspace \x08) that might be sent
        # alongside the key event, to avoid double-handling or corrupting the buffer.
        filtered = "".join(ch for ch in text if ord(ch) >= 32 and ch != "\x7f")
        if filtered:
            controller.manager.feed_text(filtered)
        return

    main_menu = getattr(window, "main_menu_overlay", None)
    if main_menu is not None and getattr(main_menu, "visible", False):
        handler = getattr(main_menu, "on_text", None)
        if callable(handler):
            handler(text)
        return

    browser = getattr(window, "dev_browser_overlay", None)
    if browser is not None and getattr(browser, "visible", False):
        handler = getattr(browser, "on_text", None)
        if callable(handler):
            handler(text)
        return

    if window.editor_controller.active:
        window.editor_controller.handle_text_input(text)


def player_input_blocked(controller: "InputController") -> bool:
    if controller.is_input_locked():
        return True
    if controller.window.ui_controller.input_blocked:
        return True
    cs = getattr(controller.window, "cutscene_controller", None)
    if cs is not None and getattr(cs, "is_running", False):
        return True
    return False
