from __future__ import annotations

from typing import Any

import engine.optional_arcade as optional_arcade

from engine.editor.editor_panels_query import panels_is_open
from engine.input_runtime.capture_runtime_focus_model import CaptureFocusSnapshot


def _get_modifiers(window: Any, modifiers: int | None) -> int:
    if modifiers is not None:
        return int(modifiers)
    return int(getattr(window, "_debug_last_modifiers", 0) or 0)


def _get_session_snapshot(editor: Any) -> Any | None:
    session = getattr(editor, "session", None) if editor is not None else None
    getter = getattr(session, "get_snapshot", None) if session is not None else None
    if callable(getter):
        return getter()
    return None


def _get_dock_snapshot(editor: Any) -> Any | None:
    dock = getattr(editor, "dock", None) if editor is not None else None
    getter = getattr(dock, "get_snapshot", None) if dock is not None else None
    if callable(getter):
        return getter()
    return dock


def get_capture_focus_snapshot(controller: Any, modifiers: int | None = None) -> CaptureFocusSnapshot:
    window = controller.window
    editor = getattr(window, "editor_controller", None)
    editor_active = bool(editor and getattr(editor, "active", False))

    session_snapshot = _get_session_snapshot(editor)
    dock_snapshot = _get_dock_snapshot(editor) if editor_active else None

    is_confirm_modal_open = bool(editor and panels_is_open(editor, "confirm_modal"))
    is_context_menu_open = bool(
        editor
        and (panels_is_open(editor, "context_menu") or panels_is_open(editor, "project_context_menu"))
    )

    keybinds = getattr(editor, "keybinds", None) if editor else None
    keybinds_state = getattr(keybinds, "state", None) if keybinds else None
    is_keybinds_open = bool(keybinds_state and getattr(keybinds_state, "visible", False))
    is_keybinds_recording = bool(keybinds_state and getattr(keybinds_state, "recording", False))

    project_explorer = getattr(editor, "project_explorer", None) if editor else None
    is_inline_rename_active = bool(
        project_explorer is not None
        and getattr(project_explorer, "inline_rename_active", False)
    )

    is_command_palette_open = bool(getattr(window, "command_palette_enabled", False))
    is_command_palette_prompt_active = bool(getattr(window, "command_palette_prompt_active", False))

    console = getattr(window, "console_controller", None)
    is_console_active = bool(console and getattr(console, "active", False))

    is_project_explorer_focused = False
    if editor_active:
        if session_snapshot is not None:
            is_project_explorer_focused = bool(
                getattr(session_snapshot, "project_explorer_focused", False)
            )
        else:
            left_tab = str(getattr(dock_snapshot, "left_tab", "") or "")
            is_project_explorer_focused = left_tab == "Project"
        if is_context_menu_open or is_inline_rename_active:
            is_project_explorer_focused = False

    is_problems_focused = False
    if editor_active:
        if session_snapshot is not None:
            is_problems_focused = bool(
                getattr(session_snapshot, "problems_panel_focused", False)
            )
        else:
            left_tab = str(getattr(dock_snapshot, "left_tab", "") or "")
            right_tab = str(getattr(dock_snapshot, "right_tab", "") or "")
            is_problems_focused = left_tab == "Problems" or right_tab == "Problems"

    palette_state = None
    try:
        from engine.palette_mode import get_state  # noqa: PLC0415

        palette_state = get_state()
    except Exception:  # noqa: BLE001  # REASON: optional palette-mode state checks should fall back to no palette focus capture
        palette_state = None
    is_palette_mode_enabled = bool(palette_state and getattr(palette_state, "enabled", False))

    if session_snapshot is not None:
        is_capture_mode_enabled = bool(getattr(session_snapshot, "capture_mode_active", False))
        is_tile_paint_enabled = bool(getattr(session_snapshot, "tile_paint_active", False))
        is_entity_paint_enabled = bool(getattr(session_snapshot, "entity_paint_active", False))
        is_authoring_selected = bool(getattr(session_snapshot, "authoring_selected_active", False))
    else:
        capture_state = getattr(window, "capture_state", None)
        is_capture_mode_enabled = bool(capture_state and getattr(capture_state, "enabled", False))
        tile_paint_state = getattr(window, "tile_paint_state", None)
        is_tile_paint_enabled = bool(tile_paint_state and getattr(tile_paint_state, "enabled", False))
        entity_paint_state = getattr(window, "entity_paint_state", None)
        is_entity_paint_enabled = bool(entity_paint_state and getattr(entity_paint_state, "enabled", False))
        authoring_selected_id = getattr(window, "authoring_selected_entity_id", None)
        is_authoring_selected = bool(authoring_selected_id)

    entity_select_state = getattr(window, "entity_select_state", None)
    selected_ids = getattr(entity_select_state, "selected_ids", None) if entity_select_state else None
    is_entity_select_active = bool(
        entity_select_state
        and isinstance(selected_ids, list)
        and selected_ids
    )

    ui_ctrl = getattr(window, "ui_controller", None)
    ui_blocked = bool(ui_ctrl and getattr(ui_ctrl, "input_blocked", False))

    scene_persist_armed = bool(getattr(window, "scene_persist_armed", False))
    show_debug = bool(getattr(window, "show_debug", False))

    mods = _get_modifiers(window, modifiers)
    ctrl = bool(mods & optional_arcade.arcade.key.MOD_CTRL)
    alt = bool(mods & optional_arcade.arcade.key.MOD_ALT)
    shift = bool(mods & optional_arcade.arcade.key.MOD_SHIFT)

    return CaptureFocusSnapshot(
        is_confirm_modal_open=is_confirm_modal_open,
        is_context_menu_open=is_context_menu_open,
        is_keybinds_recording=is_keybinds_recording,
        is_keybinds_open=is_keybinds_open,
        is_inline_rename_active=is_inline_rename_active,
        is_command_palette_open=is_command_palette_open,
        is_command_palette_prompt_active=is_command_palette_prompt_active,
        is_console_active=is_console_active,
        is_project_explorer_focused=is_project_explorer_focused,
        is_problems_focused=is_problems_focused,
        is_palette_mode_enabled=is_palette_mode_enabled,
        is_capture_mode_enabled=is_capture_mode_enabled,
        is_tile_paint_enabled=is_tile_paint_enabled,
        is_entity_paint_enabled=is_entity_paint_enabled,
        is_entity_select_active=is_entity_select_active,
        is_authoring_selected=is_authoring_selected,
        show_debug=show_debug,
        editor_active=editor_active,
        ui_blocked=ui_blocked,
        scene_persist_armed=scene_persist_armed,
        ctrl=ctrl,
        alt=alt,
        shift=shift,
    )
