"""Focus controller for editor focus and input modes."""
from __future__ import annotations

from typing import Any

from engine.editor.editor_focus_model import (
    compute_active_shortcut_scopes,
    derive_focus_target_for_controller,
    is_text_input_active_for_controller,
)


class EditorFocusController:
    def __init__(self, controller: Any) -> None:
        self._controller = controller

    def get_focus_snapshot(self) -> dict[str, Any]:
        focus_target = derive_focus_target_for_controller(self._controller)
        text_input_active = is_text_input_active_for_controller(focus_target, self._controller)
        scopes = compute_active_shortcut_scopes(focus_target, {})
        return {
            "focus_target": focus_target,
            "text_input_active": text_input_active,
            "scopes": scopes,
        }
