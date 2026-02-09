from __future__ import annotations

from typing import TYPE_CHECKING

from engine.editor.editor_actions import run_editor_action

from .editor_input_router import route_and_dispatch as route_editor_input
from .editor_input_legacy_handlers import handle_input_legacy
from .editor_input_key_handlers import handle_pre_routed_keys as handle_pre_routed_keys
from .editor_input_shortcut_handlers import (
    handle_editor_action_shortcut as handle_editor_action_shortcut,
    is_text_input_active as is_text_input_active,
)

if TYPE_CHECKING:
    from engine.editor_controller import EditorModeController as EditorController


def handle_input(controller: EditorController, key: int, modifiers: int) -> bool:
    """Handle keyboard input when editor is active. Returns True if consumed."""
    if not controller.active:
        return False

    if handle_pre_routed_keys(controller, key, modifiers):
        return True

    if route_editor_input(controller, key, modifiers):
        return True

    if handle_editor_action_shortcut(controller, key, modifiers):
        return True

    return handle_input_legacy(
        controller,
        key,
        modifiers,
        is_text_input_active=is_text_input_active,
        run_action=run_editor_action,
    )
