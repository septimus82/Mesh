"""Focus controller for editor focus and input modes."""
from __future__ import annotations

from typing import Any

from engine.editor.editor_focus_model import (
    collect_editor_state,
    compute_active_shortcut_scopes,
    derive_focus_target,
    is_text_input_active,
)


class EditorFocusController:
    def __init__(self, controller: Any) -> None:
        self._controller = controller

    def get_focus_snapshot(self) -> dict[str, Any]:
        state_dict = collect_editor_state(self._controller)
        focus_target = derive_focus_target(state_dict)
        text_input_active = is_text_input_active(focus_target, state_dict)
        scopes = compute_active_shortcut_scopes(focus_target, state_dict)
        return {
            "focus_target": focus_target,
            "text_input_active": text_input_active,
            "scopes": scopes,
        }