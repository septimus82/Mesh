from __future__ import annotations

from typing import Any, TYPE_CHECKING
from engine.swallowed_exceptions import _log_swallow

from engine.editor.editor_actions import get_editor_actions, run_editor_action
from engine.editor.shortcut_resolver_model import (
    build_shortcut_map_by_scope,
    normalize_shortcut_event,
    resolve_shortcut_scoped,
)
from engine.editor.editor_focus_model import (
    compute_active_shortcut_scopes,
    derive_focus_target_for_controller,
    is_text_input_active_for_controller,
)


if TYPE_CHECKING:
    from engine.editor_controller import EditorModeController as EditorController


def get_focus_snapshot(controller: "EditorController") -> dict[str, Any]:
    focus_ctl = getattr(controller, "focus", None)
    if focus_ctl is not None:
        getter = getattr(focus_ctl, "get_focus_snapshot", None)
        if callable(getter):
            result = getter()
            if isinstance(result, dict):
                return result
    focus_target = derive_focus_target_for_controller(controller)
    return {
        "focus_target": focus_target,
        "text_input_active": is_text_input_active_for_controller(focus_target, controller),
        "scopes": compute_active_shortcut_scopes(focus_target, {}),
    }


def is_text_input_active(controller: "EditorController") -> bool:
    snapshot = get_focus_snapshot(controller)
    return bool(snapshot.get("text_input_active", False))


def get_active_shortcut_scopes(controller: "EditorController") -> list[str]:
    snapshot = get_focus_snapshot(controller)
    scopes = snapshot.get("scopes")
    return list(scopes) if isinstance(scopes, tuple) else list(scopes or [])


def handle_editor_action_shortcut(controller: "EditorController", key: int, modifiers: int) -> bool:
    """Handle shortcut dispatch using scoped resolution.

    Uses shortcut scopes to resolve conflicts:
    - Scoped shortcuts (like inline rename) take priority when their scope is active
    - Global shortcuts are the fallback
    """
    shortcut = normalize_shortcut_event(key, modifiers)
    if not shortcut:
        return False
    # Skip single alphanumeric characters without modifiers (let text input handle them)
    if "+" not in shortcut and len(shortcut) == 1 and shortcut.isalnum():
        return False

    window = getattr(controller, "window", None)
    if window is not None and getattr(window, "editor_controller", None) is None:
        try:
            window.editor_controller = controller
        except Exception:
            _log_swallow("EDIT-001", "engine/editor_runtime/editor_input_shortcut_handlers.py pass-only blanket swallow")
            pass

    actions = get_editor_actions(controller, window)
    scope_maps = build_shortcut_map_by_scope(actions)
    active_scopes = get_active_shortcut_scopes(controller)

    # Resolve using scoped priority
    action_id = resolve_shortcut_scoped(scope_maps, shortcut, active_scopes)
    if not action_id:
        return False

    # Check if action is enabled
    if not _action_is_enabled(actions, action_id, controller, window):
        return False

    return run_editor_action(action_id, controller, window)


def _action_is_enabled(actions: list[Any], action_id: str, controller: Any, window: Any) -> bool:
    """Check if an action is enabled by its ID."""
    for action in actions:
        if getattr(action, "id", None) == action_id:
            enabled_fn = getattr(action, "enabled", None)
            if callable(enabled_fn):
                return bool(enabled_fn(controller, window))
            return True
    return False
