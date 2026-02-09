from __future__ import annotations

from typing import Any

import engine.optional_arcade as optional_arcade
from engine.editor.editor_panels_query import panels_is_open
from engine.editor.editor_focus_model import (
    FOCUS_COMMAND_PALETTE,
    compute_active_shortcut_scopes,
    derive_focus_target_for_controller,
    is_text_input_active_for_controller,
)
from engine.editor.editor_session_query import get_session_snapshot
from engine.editor.editor_command_palette_controller import (
    activate as command_palette_activate,
    backspace as command_palette_backspace,
    close_palette as command_palette_close,
    move_down as command_palette_down,
    move_up as command_palette_up,
)

from .editor_input_router_model import (
    KeyCombo,
    SCOPE_COMMAND_PALETTE,
    SCOPE_KEYBINDS,
    build_route_table,
    resolve_route,
)

_ROUTES = build_route_table()


def _build_focus_snapshot(controller: Any) -> dict[str, Any]:
    session_snapshot = get_session_snapshot(controller)
    focus_target = derive_focus_target_for_controller(controller, session_snapshot=session_snapshot)
    return {
        "focus_target": focus_target,
        "text_input_active": is_text_input_active_for_controller(focus_target, controller),
        "scopes": compute_active_shortcut_scopes(focus_target, {}),
    }


def _normalize_modifiers(modifiers: int) -> int:
    k = optional_arcade.arcade.key
    mask = int(getattr(k, "MOD_SHIFT", 0) or 0) | int(getattr(k, "MOD_CTRL", 0) or 0) | int(
        getattr(k, "MOD_ALT", 0) or 0
    )
    mask |= int(getattr(k, "MOD_COMMAND", 0) or 0)
    return int(modifiers) & mask


def route_and_dispatch(
    controller: Any,
    key: int,
    modifiers: int,
    snapshot: dict[str, Any] | None = None,
) -> bool:
    snap = snapshot if isinstance(snapshot, dict) else _build_focus_snapshot(controller)
    focus_target = snap.get("focus_target", "")
    text_input_active = bool(snap.get("text_input_active", False))
    active_scopes = list(snap.get("scopes") or [])

    command_palette_open = panels_is_open(controller, "command_palette")
    if focus_target == FOCUS_COMMAND_PALETTE or command_palette_open:
        if SCOPE_COMMAND_PALETTE not in active_scopes:
            active_scopes.insert(0, SCOPE_COMMAND_PALETTE)

    keybinds_ctrl = getattr(controller, "keybinds", None)
    keybinds_state = getattr(keybinds_ctrl, "state", None)
    keybinds_visible = bool(getattr(keybinds_state, "visible", False))
    if keybinds_visible and SCOPE_KEYBINDS not in active_scopes:
        active_scopes.insert(0, SCOPE_KEYBINDS)

    predicate_results = {
        "always": True,
        "when_not_text_input": not text_input_active,
        "when_command_palette": command_palette_open,
        "when_keybinds": keybinds_visible,
        "when_command_palette_toggle_allowed": (not text_input_active) or (focus_target == FOCUS_COMMAND_PALETTE),
    }

    combo = KeyCombo(int(key), _normalize_modifiers(modifiers))
    action_id = resolve_route(active_scopes, combo, _ROUTES, predicate_results)
    if not action_id:
        return False

    handler = _DISPATCHERS.get(action_id)
    if handler is not None:
        return bool(handler(controller, key, modifiers))

    if action_id == "editor.keybinds.modal.input":
        handler = getattr(keybinds_ctrl, "handle_input", None)
        if callable(handler):
            return bool(handler(key, modifiers))
        return False

    runner = getattr(controller, "run_editor_action", None)
    if callable(runner):
        return bool(runner(action_id))
    return False


_DISPATCHERS: dict[str, Any] = {
    "editor.command_palette.close": lambda ctrl, _key, _mods: command_palette_close(ctrl),
    "editor.command_palette.backspace": lambda ctrl, _key, _mods: command_palette_backspace(ctrl),
    "editor.command_palette.up": lambda ctrl, _key, _mods: command_palette_up(ctrl),
    "editor.command_palette.down": lambda ctrl, _key, _mods: command_palette_down(ctrl),
    "editor.command_palette.activate": lambda ctrl, _key, _mods: command_palette_activate(ctrl),
}
