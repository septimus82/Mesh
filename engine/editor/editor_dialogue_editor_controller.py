from __future__ import annotations

from typing import Any


class EditorDialogueEditorController:
    """Read-only browse controller for the Dialogue dock tab."""

    def __init__(self, editor: Any) -> None:
        self._editor = editor

    def is_edit_mode_active(self) -> bool:
        return False

    def handle_dialogue_editor_text_input(self, text: str) -> bool:  # noqa: ARG002
        return False

    def handle_dialogue_editor_key(self, key: int, modifiers: int) -> bool:  # noqa: ARG002
        return False

    def handle_dialogue_editor_mouse_click(self, x: float, y: float) -> bool:
        window = getattr(self._editor, "window", None)
        overlay = getattr(window, "dialogue_editor_overlay", None)
        if overlay is None:
            return True
        index = overlay.row_index_at(float(x), float(y))
        if index is not None:
            overlay.set_selected_index(index)
        return True
