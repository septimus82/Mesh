"""Contract tests for debounced workspace autosave controller wiring."""

from __future__ import annotations

from engine.editor.workspace_autosave_model import mark_flushed
from engine.editor_controller import WORKSPACE_AUTOSAVE_DELAY_NS
from engine.editor.editor_workspace_controller import EditorWorkspaceController
from engine.editor_runtime import input as editor_input


class _StubEditor:
    def __init__(self) -> None:
        self.window = object()


class _StubWorkspace(EditorWorkspaceController):
    def __init__(self) -> None:
        super().__init__(_StubEditor())
        self.save_calls = 0

    def save_workspace(self) -> None:
        self.save_calls += 1
        self._autosave_state = mark_flushed(self._autosave_state, 1234)


def test_tick_skips_during_text_input(monkeypatch) -> None:
    stub = _StubWorkspace()
    stub.schedule_autosave(now_ns=0)

    monkeypatch.setattr(editor_input, "_is_text_input_active", lambda _c: True)
    stub.tick_autosave(delay_ns=WORKSPACE_AUTOSAVE_DELAY_NS, now_ns=WORKSPACE_AUTOSAVE_DELAY_NS + 1)
    assert stub.save_calls == 0

    monkeypatch.setattr(editor_input, "_is_text_input_active", lambda _c: False)
    stub.tick_autosave(delay_ns=WORKSPACE_AUTOSAVE_DELAY_NS, now_ns=WORKSPACE_AUTOSAVE_DELAY_NS + 1)
    assert stub.save_calls == 1
