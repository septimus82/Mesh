from __future__ import annotations

from engine.editor.editor_panels_controller import EditorPanelsController


class _FakeWindow:
    width = 1280
    height = 720
    text_cache = None


class _FakeEditor:
    def __init__(self) -> None:
        self.window = _FakeWindow()
        self._keymap_overrides = {}

    def _handle_context_menu_input(self, key: int, modifiers: int) -> bool:  # noqa: ARG002
        return False


def test_panels_open_close_updates_ui_stack_state() -> None:
    editor = _FakeEditor()
    panels = EditorPanelsController(editor)

    assert editor.ui_layers._state.active_modal_id is None
    panels.open_keybinds()
    assert editor.ui_layers._state.active_modal_id == "keybinds"
    panels.open_confirm_modal()
    assert editor.ui_layers._state.active_modal_id == "confirm_modal"
    panels.close_confirm_modal()
    assert editor.ui_layers._state.active_modal_id == "keybinds"
