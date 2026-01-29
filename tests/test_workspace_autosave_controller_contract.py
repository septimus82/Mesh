"""Contract tests for debounced workspace autosave controller wiring."""

from __future__ import annotations

from engine.editor.workspace_autosave_model import AutosaveState, mark_flushed
from engine.editor_controller import EditorModeController, WORKSPACE_AUTOSAVE_DELAY_NS
from engine.editor_runtime import input as editor_input


class _StubController:
    def __init__(self) -> None:
        self._workspace_autosave_state = AutosaveState()
        self.save_calls = 0

    def save_workspace(self) -> None:
        self.save_calls += 1
        self._workspace_autosave_state = mark_flushed(self._workspace_autosave_state, 1234)


def test_tick_skips_during_text_input(monkeypatch) -> None:
    stub = _StubController()
    EditorModeController._autosave_workspace(stub, now_ns=0)

    monkeypatch.setattr(editor_input, "_is_text_input_active", lambda _c: True)
    EditorModeController._tick_workspace_autosave(stub, now_ns=WORKSPACE_AUTOSAVE_DELAY_NS + 1)
    assert stub.save_calls == 0

    monkeypatch.setattr(editor_input, "_is_text_input_active", lambda _c: False)
    EditorModeController._tick_workspace_autosave(stub, now_ns=WORKSPACE_AUTOSAVE_DELAY_NS + 1)
    assert stub.save_calls == 1
